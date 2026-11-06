import os,json,time,secrets,hmac,hashlib,urllib.request,urllib.error
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
ROOT=Path(__file__).parent
catalog=json.loads((ROOT/'public/catalog.json').read_text(encoding='utf-8'))
ALLOWED={i['path'] for g in catalog for i in g['items']}
def canonical(v):
 if v is None:return ''
 if isinstance(v,bool):return str(v).lower()
 if isinstance(v,(dict,list)):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
 return str(v)
def sign(params,path,secret):
 controller,action=path.split('/')[-2:]
 plain='\n'.join(['POST',controller.lower(),action.lower(),'&'.join(k+'='+canonical(params[k]) for k in sorted(params) if k!='sign')])
 return hmac.new(secret.encode(),plain.encode(),hashlib.sha256).hexdigest()
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT/'public'),**kw)
 def reply(self,status,data):
  body=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
 def do_GET(self):
  if self.path=='/api/status':return self.reply(200,{'configured':bool(os.getenv('MERCHANT_APP_ID') and os.getenv('MERCHANT_SECRET'))})
  super().do_GET()
 def do_POST(self):
  if self.path!='/api/call':return self.reply(404,{'msg':'不存在'})
  origin=self.headers.get('Origin')
  allowed_origin=os.getenv('PUBLIC_ORIGIN','http://'+self.headers.get('Host','')).rstrip('/')
  if origin and origin!=allowed_origin:return self.reply(403,{'msg':'来源不允许'})
  token=os.getenv('MANAGER_TOKEN','')
  if not token or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):return self.reply(401,{'msg':'请填写管理访问令牌'})
  try:
   size=int(self.headers.get('Content-Length',0))
   if not 0<size<12000000:raise ValueError('请求大小不允许')
   body=json.loads(self.rfile.read(size));path=body['path'];params=body.get('params',{})
   if path not in ALLOWED or not isinstance(params,dict):raise ValueError('接口或参数无效')
   if any(k in params for k in ['app_id','timestamp','nonce','sign']):raise ValueError('不能覆盖认证参数')
   app=os.getenv('MERCHANT_APP_ID');secret=os.getenv('MERCHANT_SECRET')
   if not app or not secret:return self.reply(503,{'msg':'尚未配置平台应用凭证'})
   params.update(app_id=app,timestamp=int(time.time()),nonce=secrets.token_hex(16));params['sign']=sign(params,path,secret)
   req=urllib.request.Request('https://www.16688.com.cn'+path,data=json.dumps(params,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'},method='POST')
   with urllib.request.urlopen(req,timeout=30) as r:result=json.load(r)
   self.reply(200,result)
  except (ValueError,KeyError) as e:self.reply(400,{'msg':str(e)})
  except Exception:self.reply(502,{'msg':'平台请求失败，请检查网络和服务端配置'})
if __name__=='__main__':
 port=int(os.getenv('PORT','8765'));host=os.getenv('BIND_HOST','127.0.0.1')
 print(f'商家管理服务端口：{port}');ThreadingHTTPServer((host,port),Handler).serve_forever()
