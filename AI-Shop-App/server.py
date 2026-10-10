"""Local Zhixuan shop. Python standard library only; real payments are disabled."""
import argparse
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'
DATA = Path(os.environ.get('SHOP_DATA_DIR', str(ROOT / 'data'))).resolve()
SESSION_SECONDS = 7 * 24 * 3600
ROUNDS = 310000
LIMIT_LOCK = threading.Lock()
ATTEMPTS = {}


class Error(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def db():
    con = sqlite3.connect(DATA / 'shop.sqlite3', timeout=20)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con


def text(value, name, limit=200, minimum=1):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= limit:
        raise Error(f'{name}需要 {minimum}–{limit} 个字符')
    return value.strip()


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise Error(f'{name}应为 {low}–{high} 的整数')
    return value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        raise Error('密码需为 10–128 个字符')
    salt = secrets.token_hex(16)
    result = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), ROUNDS).hex()
    return salt + ':' + result


def password_ok(password, stored):
    if not isinstance(password, str) or len(password) > 128:
        return False
    salt, expected = stored.split(':')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), ROUNDS).hex()
    return hmac.compare_digest(actual, expected)


def initialize():
    DATA.mkdir(parents=True, exist_ok=True)
    with closing(db()) as c, c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
          nickname TEXT NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'customer', created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), csrf TEXT NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, cents INTEGER NOT NULL,
          category TEXT NOT NULL, ios INTEGER NOT NULL, description TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS cart(user_id INTEGER REFERENCES users(id), product_id INTEGER REFERENCES products(id), qty INTEGER NOT NULL, PRIMARY KEY(user_id,product_id));
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), total INTEGER NOT NULL,
          status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', created INTEGER NOT NULL, updated INTEGER NOT NULL, request_key TEXT NOT NULL,
          UNIQUE(user_id,request_key));
        CREATE TABLE IF NOT EXISTS order_items(order_id TEXT REFERENCES orders(id), product_id INTEGER, name TEXT NOT NULL, cents INTEGER NOT NULL, qty INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, order_id TEXT REFERENCES orders(id), message TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), subject TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, ticket_id INTEGER REFERENCES tickets(id), sender TEXT NOT NULL, body TEXT NOT NULL, created INTEGER NOT NULL);
        ''')
        if not c.execute('SELECT 1 FROM settings WHERE key="initialized"').fetchone():
            seed = [('GPT Plus 30天',10899,'plus',0),('GPT Pro200（原20x）30天',99048,'pro',0),('iOS美区 GPT Plus 30天',12800,'plus',1),('美区iOS GPT Pro 20X',130000,'pro',1),('iOS美区 GPT Pro5x 30天',61850,'pro',1),('iOS美区 GPT Plus 1年',130000,'plus',1),('iOS美区 GPT Pro 500（原稿标注25x）30天',304000,'pro',1)]
            c.executemany('INSERT INTO products(name,cents,category,ios,description) VALUES(?,?,?,?,?)', [(*p,'沿用原版的商品展示信息。价格、授权及交付方式尚待商家核实，当前仅用于模拟购买，不提供真实充值或订阅交付。') for p in seed])
            c.executemany('INSERT INTO settings VALUES(?,?)',[('initialized','1'),('site_name','智选 AI 商城'),('announcement','精选数字服务，先体验，再选择。当前所有交易均为模拟。'),('support_hours','服务时间：工作日 09:00–18:00（演示）')])
        if not c.execute('SELECT 1 FROM users WHERE role="admin"').fetchone():
            key_path = DATA / 'setup-key.txt'
            if not key_path.exists():
                key_path.write_text(secrets.token_urlsafe(24), encoding='utf-8')


class Handler(BaseHTTPRequestHandler):
    server_version = 'ZhixuanLocal/2'

    def log_message(self, fmt, *args):
        # Do not log request bodies, cookies or initialization credentials.
        pass

    def respond(self, payload, status=200, cookie=None):
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.headers_common()
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(raw)))
        if cookie:
            self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(raw)

    def headers_common(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

    def session(self, c, required=False, admin=False):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie',''))
        except Exception:
            pass
        token = cookies.get('shop_session')
        session = c.execute('SELECT u.*,s.csrf,s.token FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?', (digest(token.value) if token else '', int(time.time()))).fetchone()
        if (required or admin) and not session:
            raise Error('请先登录',401)
        if admin and session['role'] != 'admin':
            raise Error('仅管理员可访问',403)
        if session and self.command != 'GET' and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']):
            raise Error('会话验证失败，请刷新后重试',403)
        return session

    def new_session(self, c, user_id):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        c.execute('DELETE FROM sessions WHERE expires<?',(int(time.time()),))
        c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(digest(token),user_id,csrf,int(time.time())+SESSION_SECONDS))
        self.cookie = f'shop_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_SECONDS}'

    def body(self):
        if self.headers.get('Origin') != f'http://{self.headers.get("Host")}':
            raise Error('请求来源无效',403)
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
            raise Error('需要 JSON 请求',415)
        try:
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 65536:
                raise Error('请求内容过大或为空',413)
            value = json.loads(self.rfile.read(size))
            if not isinstance(value,dict):
                raise Error('请求格式不正确')
            return value
        except (ValueError,UnicodeError):
            raise Error('请求格式不正确')

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        self.cookie = None
        try:
            port = self.server.server_address[1]
            if self.headers.get('Host') not in (f'127.0.0.1:{port}',f'localhost:{port}'):
                raise Error('本地版本仅允许本机访问',403)
            path = urlsplit(self.path).path
            if path.startswith('/api/'):
                body = self.body() if self.command == 'POST' else {}
                c = db()
                try:
                    with c:
                        if self.command == 'POST':
                            c.execute('BEGIN IMMEDIATE')
                        result = self.api(c,path,body)
                finally:
                    c.close()
                self.respond(result,cookie=self.cookie)
            elif self.command == 'GET':
                self.static(path)
            else:
                raise Error('页面不存在',404)
        except Error as exc:
            self.respond({'error':exc.message},exc.status)
        except sqlite3.IntegrityError:
            self.respond({'error':'信息冲突，请刷新后重试'},409)
        except Exception:
            self.respond({'error':'暂时无法完成操作，请稍后重试'},500)

    def static(self, path):
        # Explicit allowlist: database and source can never be served.
        files = {'/':'index.html','/admin':'admin.html','/admin/':'admin.html','/app.js':'app.js','/admin.js':'admin.js','/common.js':'common.js','/style.css':'style.css','/assets/ai-hero.png':'assets/ai-hero.png','/favicon.svg':'favicon.svg'}
        if path not in files:
            raise Error('页面不存在',404)
        target = PUBLIC / files[path]
        raw = target.read_bytes()
        self.send_response(200)
        self.headers_common()
        self.send_header('Content-Type',(mimetypes.guess_type(target)[0] or 'application/octet-stream') + ('; charset=utf-8' if target.suffix in ('.html','.js','.css','.svg') else ''))
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-cache')
        self.end_headers()
        self.wfile.write(raw)

    def public_user(self,u):
        return {k:u[k] for k in ('id','username','nickname','role')} if u else None

    def orders(self,c,user=None):
        rows = c.execute('SELECT o.*,u.nickname,u.username FROM orders o JOIN users u ON u.id=o.user_id '+('WHERE user_id=? ' if user else '')+'ORDER BY created DESC,o.rowid DESC',(user['id'],) if user else ()).fetchall()
        result=[]
        for row in rows:
            o=dict(row)
            o['items']=[dict(x) for x in c.execute('SELECT product_id,name,cents,qty FROM order_items WHERE order_id=?',(o['id'],))]
            o['events']=[dict(x) for x in c.execute('SELECT message,created FROM events WHERE order_id=? ORDER BY id',(o['id'],))]
            result.append(o)
        return result

    def event(self,c,order_id,message):
        c.execute('INSERT INTO events(order_id,message,created) VALUES(?,?,?)',(order_id,message,int(time.time())))

    def api(self,c,path,b):
        now=int(time.time())
        if self.command=='GET':
            if path=='/api/health': return {'ok':True,'mode':'demo','version':2}
            if path=='/api/catalog':
                return {'products':[dict(p) for p in c.execute('SELECT * FROM products WHERE active=1 ORDER BY id')], 'settings':dict(c.execute('SELECT key,value FROM settings WHERE key!="initialized"').fetchall())}
            if path=='/api/me':
                u=self.session(c)
                return {'user':self.public_user(u),'csrf':u['csrf'] if u else None,'setup_needed':not bool(c.execute('SELECT 1 FROM users WHERE role="admin"').fetchone())}
            if path=='/api/cart':
                u=self.session(c,required=True)
                return {'items':[dict(x) for x in c.execute('SELECT p.*,ct.qty FROM cart ct JOIN products p ON p.id=ct.product_id WHERE user_id=? ORDER BY p.id',(u['id'],))]}
            if path=='/api/orders': return {'orders':self.orders(c,self.session(c,required=True))}
            if path=='/api/tickets':
                u=self.session(c,required=True)
                tickets=[dict(x) for x in c.execute('SELECT t.*,u.nickname FROM tickets t JOIN users u ON u.id=t.user_id '+('' if u['role']=='admin' else 'WHERE user_id=? ')+'ORDER BY t.id DESC',() if u['role']=='admin' else (u['id'],))]
                for t in tickets:
                    t['messages']=[dict(x) for x in c.execute('SELECT sender,body,created FROM messages WHERE ticket_id=? ORDER BY id',(t['id'],))]
                return {'tickets':tickets}
            if path=='/api/admin':
                self.session(c,admin=True)
                return {'products':[dict(x) for x in c.execute('SELECT * FROM products ORDER BY id')],'orders':self.orders(c),'users':[dict(x) for x in c.execute('SELECT id,username,nickname,role,created FROM users ORDER BY id DESC')], 'settings':dict(c.execute('SELECT key,value FROM settings WHERE key!="initialized"').fetchall())}
            raise Error('接口不存在',404)

        if path in ('/api/register','/api/login','/api/setup'):
            username=text(b.get('username'),'用户名',30,3).lower()
            if not re.fullmatch(r'[a-z0-9_]{3,30}',username): raise Error('用户名使用 3–30 位字母、数字或下划线')
            bucket=(self.client_address[0],username)
            with LIMIT_LOCK:
                recent=[t for t in ATTEMPTS.get(bucket,[]) if t>now-900]
                global_key=(self.client_address[0],'*')
                global_recent=[t for t in ATTEMPTS.get(global_key,[]) if t>now-900]
                if len(recent)>=12 or len(global_recent)>=100: raise Error('尝试次数过多，请 15 分钟后重试',429)
                ATTEMPTS[bucket]=recent+[now]
                ATTEMPTS[global_key]=global_recent+[now]
            if path=='/api/login':
                row=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
                if not password_ok(b.get('password'),row['password'] if row else '0'*32+':'+'0'*64) or not row: raise Error('用户名或密码不正确',401)
                user_id=row['id']
            else:
                role='customer'
                if path=='/api/setup':
                    if c.execute('SELECT 1 FROM users WHERE role="admin"').fetchone(): raise Error('管理员已经设置，请登录',409)
                    keyfile=DATA/'setup-key.txt'
                    if not isinstance(b.get('setup_key'),str) or not hmac.compare_digest(b['setup_key'],keyfile.read_text(encoding='utf-8').strip()): raise Error('初始化码不正确，请查看启动窗口或本机初始化码文件',403)
                    role='admin'
                nickname=text(b.get('nickname'),'昵称',30)
                hashed=password_hash(b.get('password'))
                if c.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone(): raise Error('用户名已被使用',409)
                user_id=c.execute('INSERT INTO users(username,nickname,password,role,created) VALUES(?,?,?,?,?)',(username,nickname,hashed,role,now)).lastrowid
            self.new_session(c,user_id)
            with LIMIT_LOCK: ATTEMPTS.pop(bucket,None)
            return {'ok':True}

        u=self.session(c,required=True,admin=path.startswith('/api/admin/'))
        if path=='/api/logout':
            c.execute('DELETE FROM sessions WHERE token=?',(u['token'],))
            self.cookie='shop_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
            return {'ok':True}
        if path=='/api/profile':
            c.execute('UPDATE users SET nickname=? WHERE id=?',(text(b.get('nickname'),'昵称',30),u['id']))
            return {'ok':True}
        if path=='/api/password':
            if not password_ok(b.get('old_password'),u['password']): raise Error('原密码不正确')
            hashed=password_hash(b.get('password'))
            c.execute('UPDATE users SET password=? WHERE id=?',(hashed,u['id']))
            c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
            self.new_session(c,u['id'])
            return {'ok':True}
        if path=='/api/cart':
            pid=integer(b.get('product_id'),'商品编号',1,1000000)
            qty=integer(b.get('qty'),'数量',0,99)
            p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
            if not p or (qty and not p['active']): raise Error('商品已下架或不存在',409)
            if qty: c.execute('INSERT INTO cart VALUES(?,?,?) ON CONFLICT(user_id,product_id) DO UPDATE SET qty=excluded.qty',(u['id'],pid,qty))
            else: c.execute('DELETE FROM cart WHERE user_id=? AND product_id=?',(u['id'],pid))
            return {'ok':True}
        if path=='/api/orders':
            key=text(b.get('request_key'),'请求编号',80,8)
            previous=c.execute('SELECT id FROM orders WHERE user_id=? AND request_key=?',(u['id'],key)).fetchone()
            if previous: return {'id':previous['id']}
            items=c.execute('SELECT p.*,ct.qty FROM cart ct JOIN products p ON p.id=ct.product_id WHERE user_id=?',(u['id'],)).fetchall()
            if not items: raise Error('购物车为空')
            if any(not p['active'] for p in items): raise Error('购物车中存在已下架商品，请先移除',409)
            total=sum(p['cents']*p['qty'] for p in items)
            if b.get('expected_total')!=total: raise Error('商品价格发生变化，请刷新购物车后重新下单',409)
            oid='ZX'+time.strftime('%Y%m%d')+secrets.token_hex(4).upper()
            c.execute('INSERT INTO orders(id,user_id,total,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?)',(oid,u['id'],total,'pending',now,now,key))
            c.executemany('INSERT INTO order_items VALUES(?,?,?,?,?)',[(oid,p['id'],p['name'],p['cents'],p['qty']) for p in items])
            c.execute('DELETE FROM cart WHERE user_id=?',(u['id'],))
            self.event(c,oid,'订单已创建，等待模拟支付；不会产生真实扣款。')
            return {'id':oid}
        if path in ('/api/order/action','/api/admin/order'):
            oid=text(b.get('id'),'订单号',40)
            o=c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
            if not o or (not path.startswith('/api/admin/') and o['user_id']!=u['id']): raise Error('订单不存在',404)
            action=b.get('action')
            transitions={'pay':('pending','paid','模拟支付成功，未发生真实扣款。'),'cancel':('pending','cancelled','用户取消了待支付订单。'),'request_refund':(('paid','delivered'),'refund_requested','用户申请模拟退款。')}
            if path.startswith('/api/admin/'):
                transitions={'deliver':('paid','delivered','管理员记录了演示交付。'),'refund':(('paid','delivered','refund_requested'),'refunded','管理员完成模拟退款，未发生资金变动。')}
            if action not in transitions: raise Error('不支持的操作')
            allowed,status,message=transitions[action]
            allowed=(allowed,) if isinstance(allowed,str) else allowed
            if o['status'] not in allowed: raise Error('订单状态已变化，请刷新后重试',409)
            note=o['note']
            if action=='deliver': note=text(b.get('note'),'交付说明',1000)
            c.execute('UPDATE orders SET status=?,note=?,updated=? WHERE id=?',(status,note,now,oid))
            self.event(c,oid,message)
            return {'ok':True}
        if path=='/api/tickets/new':
            subject=text(b.get('subject'),'咨询主题',80)
            body=text(b.get('body'),'咨询内容',2000)
            tid=c.execute('INSERT INTO tickets(user_id,subject,created) VALUES(?,?,?)',(u['id'],subject,now)).lastrowid
            c.execute('INSERT INTO messages(ticket_id,sender,body,created) VALUES(?,?,?,?)',(tid,'customer',body,now))
            return {'id':tid}
        if path=='/api/tickets/reply':
            tid=integer(b.get('id'),'工单编号',1,1000000)
            t=c.execute('SELECT * FROM tickets WHERE id=?',(tid,)).fetchone()
            if not t or (u['role']!='admin' and t['user_id']!=u['id']): raise Error('咨询记录不存在',404)
            body=text(b.get('body'),'回复内容',2000)
            c.execute('INSERT INTO messages(ticket_id,sender,body,created) VALUES(?,?,?,?)',(tid,u['role'],body,now))
            c.execute('UPDATE tickets SET status=? WHERE id=?',('answered' if u['role']=='admin' else 'open',tid))
            return {'ok':True}
        if path=='/api/admin/product':
            name=text(b.get('name'),'商品名称',100)
            cents=integer(b.get('cents'),'价格（分）',1,100000000)
            category=b.get('category')
            if category not in ('plus','pro','other'): raise Error('商品分类不正确')
            ios=integer(b.get('ios'),'iOS 标记',0,1)
            active=integer(b.get('active'),'上架状态',0,1)
            description=text(b.get('description'),'商品说明',3000)
            if b.get('id') is None:
                c.execute('INSERT INTO products(name,cents,category,ios,description,active) VALUES(?,?,?,?,?,?)',(name,cents,category,ios,description,active))
            else:
                pid=integer(b['id'],'商品编号',1,1000000)
                if not c.execute('SELECT 1 FROM products WHERE id=?',(pid,)).fetchone(): raise Error('商品不存在',404)
                c.execute('UPDATE products SET name=?,cents=?,category=?,ios=?,description=?,active=? WHERE id=?',(name,cents,category,ios,description,active,pid))
            return {'ok':True}
        if path=='/api/admin/settings':
            for key,label,limit in [('site_name','商城名称',30),('announcement','商城公告',300),('support_hours','客服说明',200)]:
                c.execute('UPDATE settings SET value=? WHERE key=?',(text(b.get(key),label,limit),key))
            return {'ok':True}
        raise Error('接口不存在',404)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    initialize()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'商城：http://127.0.0.1:{args.port}/\n后台：http://127.0.0.1:{args.port}/admin',flush=True)
    with closing(db()) as con:
        if not con.execute('SELECT 1 FROM users WHERE role="admin"').fetchone():
            print('首次设置管理员，请查看本机 data/setup-key.txt 中的初始化码。',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
