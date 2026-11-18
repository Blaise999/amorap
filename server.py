"""AMORAP direct reservations. Python 3.10+; Supabase PostgreSQL backend."""
import os, sys, json, secrets, hashlib, hmac, mimetypes, re, time, base64, threading
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote
from http.cookies import SimpleCookie
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parent; PUBLIC=ROOT/'public'
load_dotenv(ROOT/'.env')
DATABASE_URL=os.environ.get('AMORAP_DATABASE_URL',''); USER=os.environ.get('AMORA_ADMIN_USER','admin'); PASSWORD=os.environ.get('AMORA_ADMIN_PASSWORD',''); SECURE=os.environ.get('AMORA_SECURE_COOKIE','0')=='1'
ATTEMPTS={}; LOCK=threading.Lock(); HOLD_SECONDS=24*3600
PREVIEW='--preview' in sys.argv
SEED=json.loads((ROOT/'seed.json').read_text(encoding='utf-8'))
class APIError(Exception):
 def __init__(self,message,status=400): super().__init__(message);self.status=status

def db():
 if PREVIEW:raise APIError('Preview only. Connect Supabase to enable bookings, contact messages and admin.',503)
 if not DATABASE_URL or any(x in DATABASE_URL for x in ('xxxxx','PROJECT_REF','YOUR_POOLER_HOST','YOUR_ENCODED_PASSWORD','[YOUR-PASSWORD]')):raise RuntimeError('Set the real Supabase Session pooler connection string in .env.')
 c=psycopg.connect(DATABASE_URL,row_factory=dict_row,connect_timeout=10,prepare_threshold=None,sslmode='require')
 # All catalog/inventory mutations serialize within this app, across processes.
 try:c.execute('SELECT pg_advisory_xact_lock(1095585618, 20261117)')
 except Exception:c.close();raise
 return c

def init():
 with db() as c:
  for k,v in SEED.items():
   c.execute('INSERT INTO amorap_booking.settings (key,value) VALUES (%s,%s) ON CONFLICT (key) DO NOTHING',(k,json.dumps(v)))
  marker=c.execute("INSERT INTO amorap_booking.settings (key,value) VALUES ('villa_photo_seed_v2','true') ON CONFLICT (key) DO NOTHING RETURNING key").fetchone()
  if marker:
   rows=get(c,'rooms');defaults={r['id']:r['images'] for r in SEED['rooms']}
   for room in rows:
    if room['id'] in defaults and not room.get('images'):room['images']=defaults[room['id']].copy()
   save(c,'rooms',rows)
  # Apply the same one-time migration used in Supabase SQL Editor.
  migration=(ROOT/'starter_catalog_upgrade.sql').read_text(encoding='utf-8')
  body=migration.split('BEGIN;',1)[1].rsplit('COMMIT;',1)[0]
  c.execute(body)

def get(c,k):return json.loads(c.execute('SELECT value FROM amorap_booking.settings WHERE key=%s',(k,)).fetchone()['value'])
def save(c,k,v):c.execute('UPDATE amorap_booking.settings SET value=%s WHERE key=%s',(json.dumps(v,ensure_ascii=False),k))
def clean(v,n=300,required=False):
 if not isinstance(v,str):raise APIError('Invalid text field.')
 v=v.strip()
 if len(v)>n or (required and not v):raise APIError('Please complete the required fields and respect text limits.')
 return v

def integer(v,lo,hi):
 if type(v) is not int or not lo<=v<=hi:raise APIError(f'Enter a whole number from {lo} to {hi}.')
 return v

def amount(v):
 if v is None or v=='':return None
 return integer(v,0,100000000)

def ident(v):
 v=clean(v,80,True)
 if not re.fullmatch('[a-zA-Z0-9_-]+',v):raise APIError('Invalid identifier.')
 return v

def enabled(r):return (r.get('active',False) and r.get('reviewed',True) and r['price'] is not None and r['price']>0 and r['capacity']>0 and r['inventory']>0)
def payment_ready(p):return all(p.get(k) for k in ('bank','name','number'))
def today():return datetime.now(timezone(timedelta(hours=8))).date()
def dates(a,b):
 try:x=date.fromisoformat(a);y=date.fromisoformat(b)
 except (TypeError,ValueError):raise APIError('Choose valid check-in and check-out dates.')
 if x<today() or not 1<=(y-x).days<=60 or x>today()+timedelta(days=730):raise APIError('Choose future stay dates for 1–60 nights.')
 return x,y

def holding(c):
 now=int(time.time());c.execute("UPDATE amorap_booking.reservations SET status='expired' WHERE status='awaiting_payment' AND expires<=%s",(now,))
 return [json.loads(r['payload']) for r in c.execute("SELECT payload FROM amorap_booking.reservations WHERE status IN ('awaiting_payment','payment_review','confirmed')")]

def quote(c,v):
 a,b=dates(v.get('checkin'),v.get('checkout')); nights=(b-a).days
 rooms={r['id']:r for r in get(c,'rooms')};extras={r['id']:r for r in get(c,'addons')}; selected=v.get('rooms'); addons=v.get('addons',[])
 if not isinstance(selected,list) or not 1<=len(selected)<=30 or not isinstance(addons,list) or len(addons)>30:raise APIError('Select at least one villa.')
 booked=holding(c); lines=[]; supplementary=[]; seen=set()
 for item in selected:
  if not isinstance(item,dict):raise APIError('Invalid villa selection.')
  rid=ident(item.get('id'));r=rooms.get(rid)
  if rid in seen or not r or not enabled(r):raise APIError('A selected villa is not currently bookable.')
  seen.add(rid);qty=integer(item.get('qty'),1,30);guests=integer(item.get('guests'),1,r['capacity']*qty)
  for day in range(nights):
   night=(a+timedelta(days=day)).isoformat();occupied=sum(l['qty'] for p in booked if p['checkin']<=night<p['checkout'] for l in p['rooms'] if l['id']==rid)
   if occupied+qty>r['inventory']:raise APIError(f"Not enough availability for {r['name']} on {night}.",409)
  lines.append({'id':rid,'name':r['name'],'qty':qty,'guests':guests,'unit':r['price'],'total':r['price']*qty*nights})
 seen=set()
 for item in addons:
  if not isinstance(item,dict):raise APIError('Invalid extra.')
  eid=ident(item.get('id'));e=extras.get(eid)
  if eid in seen or not e or not e.get('active') or e['price'] is None:raise APIError('An extra is no longer available.')
  seen.add(eid);qty=integer(item.get('qty'),1,99);supplementary.append({'id':eid,'name':e['name'],'qty':qty,'unit':e['price'],'total':e['price']*qty*(nights if e['basis']=='night' else 1),'basis':e['basis']})
 total=sum(x['total'] for x in lines+supplementary)
 return {'checkin':a.isoformat(),'checkout':b.isoformat(),'nights':nights,'rooms':lines,'addons':supplementary,'total':total,'currency':'PHP'}

def validate_rooms(c,rows):
 if not isinstance(rows,list) or len(rows)>100:raise APIError('Invalid room list.')
 result=[]; ids=set()
 for r in rows:
  if not isinstance(r,dict):raise APIError('Invalid villa.')
  rid=ident(r.get('id'))
  if rid in ids:raise APIError('Duplicate villa ID.')
  ids.add(rid);amen=r.get('amenities',[]);imgs=r.get('images',[])
  if not isinstance(amen,list) or len(amen)>40 or not isinstance(imgs,list) or len(imgs)>15:raise APIError('Invalid amenities or photos.')
  for x in imgs:
   if isinstance(x,str) and x in {im for sr in SEED['rooms'] for im in sr['images']} and (PUBLIC/x.lstrip('/')).is_file():continue
   if not isinstance(x,str) or not re.fullmatch(r'/uploads/[a-f0-9]{32}\.(jpg|png|webp)',x) or not c.execute('SELECT 1 FROM amorap_booking.photos WHERE name=%s',(Path(x).name,)).fetchone():raise APIError('Upload photos using the dashboard.')
  result.append({'id':rid,'name':clean(r.get('name'),120,True),'category':clean(r.get('category',''),100),'description':clean(r.get('description',''),3000),'price':amount(r.get('price')),'capacity':integer(r.get('capacity'),0,100),'inventory':integer(r.get('inventory'),0,1000),'bed':clean(r.get('bed',''),200),'size':clean(r.get('size',''),100),'policy':clean(r.get('policy',''),2000),'amenities':[clean(x,150,True) for x in amen],'images':imgs,'active':r.get('active') is True,'reviewed':r.get('reviewed',True) is True})
 return result

def validate_addons(rows):
 if not isinstance(rows,list) or len(rows)>100:raise APIError('Invalid extras list.')
 result=[];ids=set()
 for r in rows:
  if not isinstance(r,dict):raise APIError('Invalid extra.')
  rid=ident(r.get('id'))
  if rid in ids:raise APIError('Duplicate extra ID.')
  ids.add(rid);basis=r.get('basis')
  if basis not in ('stay','night'):raise APIError('Invalid extra pricing.')
  result.append({'id':rid,'name':clean(r.get('name'),120,True),'description':clean(r.get('description',''),1000),'price':amount(r.get('price')),'basis':basis,'active':r.get('active') is True})
 return result

def fallback_catalog():
 return {'rooms':[{**r,'bookable':False} for r in SEED['rooms'] if r['active']], 'addons':[], 'paymentReady':False,'fallback':True}

def public_catalog(c):
 return {'rooms':[{**r,'bookable':enabled(r)} for r in get(c,'rooms') if r['active']], 'addons':[r for r in get(c,'addons') if r['active'] and r['price'] is not None], 'paymentReady':payment_ready(get(c,'payment'))}

def guest(v):
 if not isinstance(v,dict):raise APIError('Enter guest details.')
 out={k:clean(v.get(k,''),n,req) for k,n,req in [('name',150,True),('email',200,True),('phone',70,True),('requests',2000,False)]}
 if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',out['email']):raise APIError('Enter a valid email address.')
 return out

def booking_record(r):
 return {'id':r['id'],'status':r['status'],'created':r['created'],'expires':r['expires'],'reference':r['reference'],**json.loads(r['payload'])}

def token_hash(t):return hashlib.sha256(t.encode()).hexdigest()
class Handler(BaseHTTPRequestHandler):
 server_version='Amora/1.0'
 def end_headers(self):
  self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'; object-src 'none'");super().end_headers()
 def respond(self,data,status=200,cookie=None):
  raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)))
  if cookie:self.send_header('Set-Cookie',cookie)
  self.end_headers();
  if self.command!='HEAD':self.wfile.write(raw)
 def body(self):
  if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise APIError('JSON required.',415)
  try:n=int(self.headers.get('Content-Length','0'))
  except ValueError:raise APIError('Invalid request.')
  if n<0 or n>9_000_000:raise APIError('Request too large.',413)
  try:r=json.loads(self.rfile.read(n))
  except (ValueError,UnicodeError):raise APIError('Invalid JSON.')
  if not isinstance(r,dict):raise APIError('Invalid request.')
  return r
 def session(self):
  try:cookie=SimpleCookie(self.headers.get('Cookie',''));t=cookie['amora_admin'].value
  except (KeyError,ValueError):return None
  with db() as c:
   s=c.execute('SELECT csrf,expiry FROM amorap_booking.admin_sessions WHERE token=%s AND expiry>%s',(token_hash(t),int(time.time()))).fetchone()
   if s:return t,s
  return None
 def admin(self,write=False):
  s=self.session()
  if not s:raise APIError('Please sign in.',401)
  if write and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s[1]['csrf']):raise APIError('Invalid session token.',403)
  return s
 def cookie(self,t,age):return f'amora_admin={t}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}'+('; Secure' if SECURE else '')
 def origin(self):
  if self.headers.get('Sec-Fetch-Site')=='cross-site':raise APIError('Cross-site request denied.',403)
  org=self.headers.get('Origin')
  if org and urlsplit(org).netloc!=self.headers.get('Host'):raise APIError('Cross-site request denied.',403)
 def do_GET(self):self.dispatch('GET')
 def do_HEAD(self):self.dispatch('HEAD')
 def do_POST(self):self.dispatch('POST')
 def do_PUT(self):self.dispatch('PUT')
 def dispatch(self,method):
  path=unquote(urlsplit(self.path).path)
  try:
   if not path.startswith('/api/'):
    if method not in ('GET','HEAD'):raise APIError('Not found.',404)
    return self.static(path)
   if method!='GET':self.origin()
   return self.api(method,path)
  except APIError as e:self.respond({'error':str(e)},e.status)
  except (BrokenPipeError,ConnectionResetError):pass
  except psycopg.OperationalError:
   print('Database connection unavailable.',flush=True)
   if path=='/api/catalog' and method=='GET':return self.respond(fallback_catalog())
   self.respond({'error':'The reservation service is temporarily unavailable. Please try again later.'},503)
  except Exception as e:
   print('Server error:',type(e).__name__,flush=True)
   if path=='/api/catalog' and method=='GET':return self.respond(fallback_catalog())
   self.respond({'error':'An unexpected server error occurred.'},500)
 def static(self,path):
  if path.startswith('/uploads/'):
   name=path.split('/')[-1]
   if not re.fullmatch(r'[a-f0-9]{32}\.(jpg|png|webp)',name):raise APIError('Not found.',404)
   with db() as c:
    photo=c.execute('SELECT content,mime FROM amorap_booking.photos WHERE name=%s',(name,)).fetchone()
   if not photo:raise APIError('Not found.',404)
   raw=bytes(photo['content']);self.send_response(200);self.send_header('Content-Type',photo['mime']);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','public, max-age=300');self.end_headers();
   if self.command!='HEAD':self.wfile.write(raw)
   return
  else:
   f=(PUBLIC/path.lstrip('/')).resolve()
   if not f.is_relative_to(PUBLIC) or any(part.startswith('.') for part in Path(path).parts[1:]):raise APIError('Not found.',404)
   if f.is_dir():
    if not path.endswith('/'):
     self.send_response(308);self.send_header('Location',path+'/'+('?' + urlsplit(self.path).query if urlsplit(self.path).query else ''));self.send_header('Content-Length','0');self.end_headers();return
    f=f/'index.html'
  if not f.is_file():raise APIError('Not found.',404)
  mime=mimetypes.guess_type(str(f))[0] or 'application/octet-stream';size=f.stat().st_size;start,end=0,size-1;partial=False
  if mime=='video/mp4' and self.headers.get('Range'):
   m=re.fullmatch(r'bytes=(\d*)-(\d*)',self.headers['Range'])
   if m and (m[1] or m[2]):
    start=int(m[1]) if m[1] else max(0,size-int(m[2]));end=min(size-1,int(m[2])) if m[1] and m[2] else size-1;partial=True
   if not m or start>end or start>=size:
    self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return
  self.send_response(206 if partial else 200);self.send_header('Content-Type',mime+('; charset=utf-8' if mime.startswith('text/') else ''));self.send_header('Content-Length',str(end-start+1));self.send_header('Cache-Control','no-store' if mime=='text/html' else 'public, max-age=300')
  if mime=='video/mp4':self.send_header('Accept-Ranges','bytes')
  if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
  self.end_headers()
  if self.command!='HEAD':
   with f.open('rb') as fp:
    fp.seek(start);left=end-start+1
    while left>0:
     chunk=fp.read(min(left,65536))
     if not chunk:break
     self.wfile.write(chunk);left-=len(chunk)
 def api(self,method,path):
  if PREVIEW:
   if path=='/api/catalog' and method=='GET':return self.respond({'rooms':[{**r,'bookable':False} for r in SEED['rooms'] if r['active']],'addons':[],'paymentReady':False,'preview':True})
   raise APIError('Preview only. Configure Supabase and restart without --preview to enable this feature.',503)
  if path=='/api/admin/login' and method=='POST':
   if len(PASSWORD)<12:raise APIError('Admin setup required: set AMORA_ADMIN_PASSWORD to at least 12 characters.',503)
   v=self.body();ip=self.client_address[0];now=time.time()
   with LOCK:
    old=[x for x in ATTEMPTS.get(ip,[]) if x>now-900];ATTEMPTS[ip]=old
    if len(old)>=8:raise APIError('Too many attempts. Try later.',429)
    old.append(now)
   if not isinstance(v.get('username'),str) or not isinstance(v.get('password'),str) or not hmac.compare_digest(v['username'].encode(),USER.encode()) or not hmac.compare_digest(v['password'].encode(),PASSWORD.encode()):raise APIError('Incorrect credentials.',401)
   t=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
   with db() as c:
    c.execute('DELETE FROM amorap_booking.admin_sessions WHERE expiry<=%s',(int(now),))
    c.execute('INSERT INTO amorap_booking.admin_sessions (token,csrf,expiry) VALUES (%s,%s,%s)',(token_hash(t),csrf,int(now)+28800))
   with LOCK:ATTEMPTS.pop(ip,None)
   return self.respond({'csrf':csrf},cookie=self.cookie(t,28800))
  if path.startswith('/api/admin/'):
   t,s=self.admin(method!='GET')
   if path=='/api/admin/session' and method=='GET':return self.respond({'csrf':s['csrf']})
   if path=='/api/admin/logout' and method=='POST':
    with db() as c:c.execute('DELETE FROM amorap_booking.admin_sessions WHERE token=%s',(token_hash(t),))
    return self.respond({'ok':True},cookie=self.cookie('',0))
   if path=='/api/admin/upload' and method=='POST':
    v=self.body();data=v.get('data','')
    if not isinstance(data,str):raise APIError('Invalid photo.')
    try:raw=base64.b64decode(data,validate=True)
    except Exception:raise APIError('Invalid photo.')
    if len(raw)>6_000_000:raise APIError('Photo exceeds 6 MB.')
    ext='jpg' if raw.startswith(b'\xff\xd8\xff') else 'png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'webp' if raw[:4]==b'RIFF' and raw[8:12]==b'WEBP' else None
    if not ext:raise APIError('Choose a JPEG, PNG or WebP photo.')
    name=secrets.token_hex(16)+'.'+ext
    mime={'jpg':'image/jpeg','png':'image/png','webp':'image/webp'}[ext]
    with db() as c:c.execute('INSERT INTO amorap_booking.photos (name,mime,content) VALUES (%s,%s,%s)',(name,mime,raw))
    return self.respond({'url':'/uploads/'+name})
   with db() as c:
    if path=='/api/admin/data' and method=='GET':
     holding(c);return self.respond({**{k:get(c,k) for k in ('rooms','addons','payment')},'bookings':[booking_record(r) for r in c.execute('SELECT * FROM amorap_booking.reservations ORDER BY created DESC')],'messages':[{'id':r['id'],'created':r['created'],**json.loads(r['payload'])} for r in c.execute('SELECT * FROM amorap_booking.messages ORDER BY created DESC')]})
    if path in ('/api/admin/rooms','/api/admin/addons','/api/admin/payment') and method=='PUT':
     v=self.body();key=path.rsplit('/',1)[1]
     if key=='rooms':val=validate_rooms(c,v.get('items'))
     elif key=='addons':val=validate_addons(v.get('items'))
     else:val={k:clean(v.get(k,''),n) for k,n in [('bank',150),('name',150),('number',150),('instructions',2000)]}
     save(c,key,val);c.commit();return self.respond({'ok':True})
    if path=='/api/admin/status' and method=='POST':
     v=self.body();rid=ident(v.get('id'));status=v.get('status'); holding(c)
     r=c.execute('SELECT * FROM amorap_booking.reservations WHERE id=%s',(rid,)).fetchone()
     if not r:raise APIError('Reservation not found.',404)
     transitions={'awaiting_payment':('confirmed','cancelled'),'payment_review':('confirmed','cancelled'),'confirmed':('cancelled',),'expired':(),'cancelled':()}
     if status not in transitions.get(r['status'],()):raise APIError('This status change is not permitted.')
     c.execute('UPDATE amorap_booking.reservations SET status=%s WHERE id=%s',(status,rid));c.commit();return self.respond({'ok':True})
   raise APIError('Not found.',404)
  with db() as c:
   if path=='/api/catalog' and method=='GET':return self.respond(public_catalog(c))
   if path=='/api/quote' and method=='POST':
    v=self.body();return self.respond(quote(c,v))
   if path=='/api/bookings' and method=='POST':
    v=self.body();person=guest(v.get('guest'));p=get(c,'payment')
    if not payment_ready(p):raise APIError('Direct payment is not configured yet. Please contact the resort.',409)
    q=quote(c,v)
    if v.get('expectedTotal') is not None and v['expectedTotal']!=q['total']:raise APIError('The price has changed. Return to checkout to review the updated total.',409)
    rid='AM-'+secrets.token_hex(5).upper();token=secrets.token_urlsafe(32);now=int(time.time());payload={**q,'guest':person,'payment':p}
    c.execute('INSERT INTO amorap_booking.reservations (id,token,status,created,expires,payload,reference) VALUES(%s,%s,%s,%s,%s,%s,%s)',(rid,token_hash(token),'awaiting_payment',now,now+HOLD_SECONDS,json.dumps(payload,ensure_ascii=False),''));c.commit()
    return self.respond({'booking':{'id':rid,'status':'awaiting_payment','expires':now+HOLD_SECONDS,**payload},'token':token},201)
   if path=='/api/booking-status' and method=='POST':
    v=self.body();rid=ident(v.get('id'));token=clean(v.get('token',''),100,True);holding(c);r=c.execute('SELECT * FROM amorap_booking.reservations WHERE id=%s',(rid,)).fetchone()
    if not r or not hmac.compare_digest(token_hash(token),r['token']):raise APIError('Reservation not found.',404)
    return self.respond({'booking':booking_record(r)})
   if path=='/api/payment-reference' and method=='POST':
    v=self.body();rid=ident(v.get('id'));token=clean(v.get('token',''),100,True);ref=clean(v.get('reference',''),200,True);holding(c);r=c.execute('SELECT * FROM amorap_booking.reservations WHERE id=%s',(rid,)).fetchone()
    if not r or not hmac.compare_digest(token_hash(token),r['token']):raise APIError('Reservation not found.',404)
    if r['status']!='awaiting_payment':raise APIError('This reservation is not awaiting payment.',409)
    c.execute("UPDATE amorap_booking.reservations SET status='payment_review', reference=%s WHERE id=%s",(ref,rid));c.commit();return self.respond({'ok':True})
   if path=='/api/contact' and method=='POST':
    v=self.body();p={'name':clean(v.get('name',''),150,True),'email':clean(v.get('email',''),200,True),'message':clean(v.get('message',''),3000,True)}
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',p['email']):raise APIError('Enter a valid email address.')
    c.execute('INSERT INTO amorap_booking.messages(created,payload) VALUES (%s,%s)',(int(time.time()),json.dumps(p)));c.commit();return self.respond({'ok':True},201)
  raise APIError('Not found.',404)

if __name__=='__main__':
 if not PREVIEW:
  try:init()
  except RuntimeError as e:sys.exit(str(e)+'\nUse python server.py --preview for a read-only local preview.')
  except psycopg.OperationalError:sys.exit('Cannot connect to Supabase. Check the exact Session pooler username, host and database password. Do not use the example URL. Use --preview to view pages locally.')
  except psycopg.Error:sys.exit('Database setup failed. Run supabase_setup.sql in the same Supabase project and check the database role permissions.')
  if len(PASSWORD)<12 or PASSWORD.startswith('replace-with-'):sys.exit('Set AMORA_ADMIN_PASSWORD to a unique strong password of at least 12 characters.')
 port=int(os.environ.get('PORT','8000'));host='127.0.0.1' if PREVIEW else os.environ.get('HOST','127.0.0.1')
 print(f'AMORAP: http://{host}:{port}/ | Admin: /admin/ | '+('READ-ONLY PREVIEW' if PREVIEW else 'Supabase connected'),flush=True)
 ThreadingHTTPServer((host,port),Handler).serve_forever()
