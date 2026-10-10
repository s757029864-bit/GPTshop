import concurrent.futures
from contextlib import closing
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

class Client:
    def __init__(self,base):
        self.base=base
        self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf=''

    def call(self,path,body=None,csrf=True,origin=True):
        headers={}
        if body is not None:
            headers['Content-Type']='application/json'
            if origin:headers['Origin']=self.base
            if csrf:headers['X-CSRF-Token']=self.csrf
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with self.opener.open(req,timeout=10) as response:
                data=json.load(response)
                if path=='/api/me':self.csrf=data.get('csrf') or ''
                return response.status,data
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code,json.load(exc)

class ShopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='zhixuan-test-')
        cls.folder=Path(cls.temp.name)
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));cls.port=s.getsockname()[1]
        cls.base=f'http://127.0.0.1:{cls.port}'
        cls.env=dict(os.environ,SHOP_DATA_DIR=str(cls.folder))
        cls.start_server()
        cls.admin=Client(cls.base)
        code,data=cls.admin.call('/api/setup',{'username':'owner','nickname':'店主','password':'OwnerPassword2026!','setup_key':(cls.folder/'setup-key.txt').read_text()})
        assert code==200,(code,data)
        cls.admin.call('/api/me')

    @classmethod
    def start_server(cls):
        cls.process=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--port',str(cls.port)],env=cls.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                if Client(cls.base).call('/api/health')[0]==200:return
            except Exception:time.sleep(.05)
        raise RuntimeError('server failed to start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate();cls.process.wait();cls.temp.cleanup()

    def setUp(self):
        self.user=Client(self.base)
        self.username='u_'+secrets.token_hex(5)
        self.assertEqual(self.user.call('/api/register',{'username':self.username,'nickname':'测试顾客','password':'CustomerPass2026!','role':'admin'})[0],200)
        self.user.call('/api/me')

    def new_product(self,cents=1234):
        p={'name':'测试商品 '+secrets.token_hex(3),'cents':cents,'category':'other','ios':0,'active':1,'description':'测试说明'}
        self.assertEqual(self.admin.call('/api/admin/product',p)[0],200)
        products=self.admin.call('/api/admin')[1]['products']
        return next(x for x in products if x['name']==p['name'])

    def order(self):
        p=self.new_product()
        self.assertEqual(self.user.call('/api/cart',{'product_id':p['id'],'qty':2})[0],200)
        body={'request_key':secrets.token_hex(10),'expected_total':2468}
        code,result=self.user.call('/api/orders',body)
        self.assertEqual(code,200,result)
        return result['id'],p,body

    def test_registration_cannot_escalate_role(self):
        self.assertEqual(self.user.call('/api/me')[1]['user']['role'],'customer')
        self.assertEqual(self.user.call('/api/admin')[0],403)
        self.assertEqual(self.user.call('/api/admin/settings',{})[0],403)

    def test_anonymous_denied(self):
        anon=Client(self.base)
        for endpoint in ['/api/admin','/api/orders','/api/cart','/api/tickets']:
            self.assertEqual(anon.call(endpoint)[0],401)

    def test_setup_is_single_use(self):
        self.assertEqual(Client(self.base).call('/api/setup',{'username':'intruder','password':'Password2026!','nickname':'x','setup_key':(self.folder/'setup-key.txt').read_text()})[0],409)

    def test_csrf_and_origin(self):
        self.assertEqual(self.user.call('/api/profile',{'nickname':'changed'},csrf=False)[0],403)
        self.assertEqual(self.user.call('/api/profile',{'nickname':'changed'},origin=False)[0],403)

    def test_cart_quantity_validation(self):
        p=self.new_product()
        for qty in [-1,100,True,1.5,'2']:
            self.assertEqual(self.user.call('/api/cart',{'product_id':p['id'],'qty':qty})[0],400)

    def test_cross_user_isolation(self):
        oid,p,_=self.order()
        other=Client(self.base)
        other.call('/api/register',{'username':'other_'+secrets.token_hex(4),'nickname':'其他用户','password':'CustomerPass2026!'})
        other.call('/api/me')
        self.assertEqual(other.call('/api/orders')[1]['orders'],[])
        self.assertEqual(other.call('/api/order/action',{'id':oid,'action':'pay'})[0],404)
        self.assertEqual(other.call('/api/cart')[1]['items'],[])
        tid=self.user.call('/api/tickets/new',{'subject':'问题','body':'咨询内容'})[1]['id']
        self.assertEqual(other.call('/api/tickets/reply',{'id':tid,'body':'越权'})[0],404)
        self.assertEqual(other.call('/api/tickets')[1]['tickets'],[])

    def test_price_authoritative_and_snapshot(self):
        p=self.new_product()
        self.user.call('/api/cart',{'product_id':p['id'],'qty':1})
        self.assertEqual(self.user.call('/api/orders',{'request_key':'changedprice','expected_total':1})[0],409)
        oid=self.user.call('/api/orders',{'request_key':'actualprice','expected_total':1234,'total':1})[1]['id']
        self.admin.call('/api/admin/product',{**p,'cents':9999,'name':'修改后的商品'})
        o=next(o for o in self.user.call('/api/orders')[1]['orders'] if o['id']==oid)
        self.assertEqual(o['total'],1234)
        self.assertEqual(o['items'][0]['name'],p['name'])

    def test_downlisted_product_blocks_checkout(self):
        p=self.new_product()
        self.user.call('/api/cart',{'product_id':p['id'],'qty':1})
        self.admin.call('/api/admin/product',{**p,'active':0})
        self.assertNotIn(p['id'],[x['id'] for x in self.user.call('/api/catalog')[1]['products']])
        self.assertEqual(self.user.call('/api/orders',{'request_key':'downlisted','expected_total':1234})[0],409)
        self.assertEqual(self.user.call('/api/cart',{'product_id':p['id'],'qty':0})[0],200)

    def test_idempotent_checkout(self):
        oid,p,body=self.order()
        self.assertEqual(self.user.call('/api/orders',body)[1]['id'],oid)
        self.assertEqual(len(self.user.call('/api/orders')[1]['orders']),1)

    def test_concurrent_checkout_only_once(self):
        p=self.new_product()
        self.user.call('/api/cart',{'product_id':p['id'],'qty':1})
        body={'request_key':'parallel-'+secrets.token_hex(5),'expected_total':1234}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.user.call('/api/orders',body),range(2)))
        self.assertTrue(all(code==200 for code,_ in results),results)
        self.assertEqual(results[0][1]['id'],results[1][1]['id'])
        self.assertEqual(len(self.user.call('/api/orders')[1]['orders']),1)

    def test_order_state_machine_and_refund(self):
        oid,_,_=self.order()
        self.assertEqual(self.admin.call('/api/admin/order',{'id':oid,'action':'deliver','note':'演示交付'})[0],409)
        self.assertEqual(self.user.call('/api/order/action',{'id':oid,'action':'deliver'})[0],400)
        self.assertEqual(self.user.call('/api/order/action',{'id':oid,'action':'pay'})[0],200)
        self.assertEqual(self.user.call('/api/order/action',{'id':oid,'action':'pay'})[0],409)
        self.assertEqual(self.admin.call('/api/admin/order',{'id':oid,'action':'deliver','note':'已完成演示交付'})[0],200)
        self.assertEqual(self.user.call('/api/orders')[1]['orders'][0]['note'],'已完成演示交付')
        self.assertEqual(self.user.call('/api/order/action',{'id':oid,'action':'request_refund'})[0],200)
        self.assertEqual(self.admin.call('/api/admin/order',{'id':oid,'action':'refund'})[0],200)
        order=self.user.call('/api/orders')[1]['orders'][0]
        self.assertEqual(order['status'],'refunded')
        self.assertEqual(len(order['events']),5)

    def test_cancel_prevents_payment(self):
        oid,_,_=self.order()
        self.assertEqual(self.user.call('/api/order/action',{'id':oid,'action':'cancel'})[0],200)
        self.assertEqual(self.user.call('/api/order/action',{'id':oid,'action':'pay'})[0],409)

    def test_support_reply(self):
        tid=self.user.call('/api/tickets/new',{'subject':'商品咨询','body':'什么时候交付？'})[1]['id']
        self.assertEqual(self.admin.call('/api/tickets/reply',{'id':tid,'body':'当前仅为演示交付。'})[0],200)
        t=self.user.call('/api/tickets')[1]['tickets'][0]
        self.assertEqual(t['status'],'answered')
        self.assertEqual(t['messages'][-1]['sender'],'admin')

    def test_password_change_invalidates_other_sessions(self):
        second=Client(self.base)
        second.call('/api/login',{'username':self.username,'password':'CustomerPass2026!'})
        second.call('/api/me')
        self.assertEqual(self.user.call('/api/password',{'old_password':'incorrect','password':'NewPassword2026!'})[0],400)
        self.assertEqual(self.user.call('/api/password',{'old_password':'CustomerPass2026!','password':'NewPassword2026!'})[0],200)
        self.user.call('/api/me')
        self.assertIsNone(second.call('/api/me')[1]['user'])
        self.assertEqual(self.user.call('/api/orders')[0],200)
        self.assertEqual(second.call('/api/login',{'username':self.username,'password':'CustomerPass2026!'})[0],401)

    def test_private_files_not_served(self):
        for path in ['/data/shop.sqlite3','/data/setup-key.txt','/server.py','/../server.py']:
            self.assertEqual(Client(self.base).call(path)[0],404)

    def test_password_not_stored_plaintext(self):
        with closing(sqlite3.connect(self.folder/'shop.sqlite3')) as c:
            password=c.execute('SELECT password FROM users WHERE username=?',(self.username,)).fetchone()[0]
        self.assertNotIn('CustomerPass',password)
        self.assertEqual(len(password.split(':')),2)

    def test_zz_restart_preserves_data_and_session(self):
        oid,_,_=self.order()
        self.process.terminate();self.process.wait()
        type(self).start_server()
        self.assertEqual(self.user.call('/api/orders')[1]['orders'][0]['id'],oid)
        self.assertIsNotNone(self.user.call('/api/me')[1]['user'])

if __name__=='__main__':unittest.main(verbosity=2)
