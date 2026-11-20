"""AMORAP direct reservations. Python 3.10+; Supabase PostgreSQL backend."""
import os, sys, json, secrets, hashlib, hmac, mimetypes, re, time, base64, threading, traceback
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote
from http.cookies import SimpleCookie, CookieError
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parent; PUBLIC=ROOT/'public'
load_dotenv(ROOT/'.env')
DATABASE_URL=os.environ.get('AMORAP_DATABASE_URL',''); USER=os.environ.get('AMORA_ADMIN_USER','admin'); PASSWORD=os.environ.get('AMORA_ADMIN_PASSWORD',''); SECURE=os.environ.get('AMORA_SECURE_COOKIE','0')=='1'
ATTEMPTS={}; LOCK=threading.Lock(); HOLD_SECONDS=24*3600
SESSION_SECONDS=24*3600
SESSION_COOKIE="amorap_admin_v3"
SESSION_RENEW_AFTER=3600
ADMIN_VERSION="20261120-simple1"
DASHBOARD_RELEASE="20261120-simple1"
PUBLIC_ORIGIN=os.environ.get("AMORA_PUBLIC_ORIGIN", "").rstrip("/")
PREVIEW='--preview' in sys.argv
SEED=json.loads((ROOT/'seed.json').read_text(encoding='utf-8'))
class APIError(Exception):
 def __init__(self,message,status=400,code=None): super().__init__(message);self.status=status;self.code=code

def db(lock=True):
 if PREVIEW:raise APIError('Preview only. Connect Supabase to enable bookings, contact messages and admin.',503)
 if not DATABASE_URL or any(x in DATABASE_URL for x in ('xxxxx','PROJECT_REF','YOUR_POOLER_HOST','YOUR_ENCODED_PASSWORD','[YOUR-PASSWORD]')):raise RuntimeError('Set the real Supabase Session pooler connection string in .env.')
 c=psycopg.connect(DATABASE_URL,row_factory=dict_row,connect_timeout=10,prepare_threshold=None,sslmode='require')
 # All catalog/inventory mutations serialize within this app, across processes.
 try:
  if lock:c.execute('SELECT pg_advisory_xact_lock(1095585618, 20261117)')
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

def decode_json(value):
 # Older deployments may use JSON/JSONB rather than the current text columns.
 return json.loads(value) if isinstance(value,(str,bytes,bytearray)) else value

def get(c,k):
 row=c.execute('SELECT value FROM amorap_booking.settings WHERE key=%s',(k,)).fetchone()
 # Serverless imports do not run init(). Populate only missing keys; never
 # replace an existing setting (including intentionally empty lists).
 if row is None and k in SEED:
  c.execute('INSERT INTO amorap_booking.settings (key,value) VALUES (%s,%s) ON CONFLICT (key) DO NOTHING',(k,json.dumps(SEED[k],ensure_ascii=False)))
  row=c.execute('SELECT value FROM amorap_booking.settings WHERE key=%s',(k,)).fetchone()
 if row is None:raise APIError('A required hotel setting is missing. Contact support. (SETTING_MISSING)',503,'SETTING_MISSING')
 try:
  value=decode_json(row['value'])
 except (ValueError,TypeError):raise APIError(f'The saved {k} settings are invalid. Contact support; existing data has not been changed.',500,'SETTING_INVALID')
 if k in SEED and not isinstance(value,type(SEED[k])):raise APIError(f'The saved {k} settings have an invalid format. Contact support; existing data has not been changed.',500,'SETTING_INVALID')
 return value
def save(c,k,v):c.execute('UPDATE amorap_booking.settings SET value=%s WHERE key=%s',(json.dumps(v,ensure_ascii=False),k))
def revision(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

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
def payment_methods(p):
 """Configured manual-payment choices; never trust a browser-selected account."""
 if not isinstance(p,dict):return []
 methods=[]
 if all(isinstance(p.get(k),str) and p[k].strip() for k in ('bank','name','number')):methods.append('bank')
 if all(isinstance(p.get(k),str) and p[k].strip() for k in ('gcashName','gcashNumber')):methods.append('gcash')
 return methods

def payment_ready(p):return bool(payment_methods(p))

def payment_snapshot(config,method):
 choices=payment_methods(config)
 if not method and len(choices)==1:method=choices[0]  # older bank-only clients
 if method not in choices:raise APIError('Choose an available payment method before reserving.',409)
 if method=='gcash':return {'method':'gcash','bank':'GCash','name':config['gcashName'],'number':config['gcashNumber'],'instructions':config.get('gcashInstructions','')}
 return {'method':'bank','bank':config['bank'],'name':config['name'],'number':config['number'],'instructions':config.get('instructions','')}

def validate_payment(v,previous=None):
 previous=previous or {}
 fields=[('bank',150),('name',150),('number',150),('instructions',2000),('gcashName',150),('gcashNumber',40),('gcashInstructions',2000)]
 out={k:clean(v.get(k,previous.get(k,'')),limit) for k,limit in fields}
 bank_fields=('bank','name','number');gcash_fields=('gcashName','gcashNumber')
 if any(out[k] for k in bank_fields) and not all(out[k] for k in bank_fields):raise APIError('Complete all local bank account fields, or leave all three blank.')
 if any(out[k] for k in gcash_fields) and not all(out[k] for k in gcash_fields):raise APIError('Enter both the GCash account name and mobile number, or leave both blank.')
 if out['gcashNumber'] and not re.fullmatch(r'(?:09\d{9}|\+639\d{9})',out['gcashNumber']):raise APIError('Enter a valid GCash number, e.g. 09XXXXXXXXX or +639XXXXXXXXX.')
 return out
def today():return datetime.now(timezone(timedelta(hours=8))).date()
def dates(a,b):
 try:x=date.fromisoformat(a);y=date.fromisoformat(b)
 except (TypeError,ValueError):raise APIError('Choose valid check-in and check-out dates.')
 if x<today() or not 1<=(y-x).days<=60 or x>today()+timedelta(days=730):raise APIError('Choose future stay dates for 1–60 nights.')
 return x,y

def expire_holds(c):
 now=int(time.time());c.execute("UPDATE amorap_booking.reservations SET status='expired' WHERE status='awaiting_payment' AND expires<=%s",(now,))

def holding(c):
 expire_holds(c)
 return [decode_json(r['payload']) for r in c.execute("SELECT payload FROM amorap_booking.reservations WHERE status IN ('awaiting_payment','payment_review','confirmed')")]

def quote(c,v):
 selected=v.get('rooms',[]); services=v.get('services',[]); addons=v.get('addons',[])
 if not isinstance(selected,list) or len(selected)>30 or not isinstance(services,list) or len(services)>30 or not isinstance(addons,list) or len(addons)>30 or not (selected or services):raise APIError('Select a villa, dining or event reservation.')
 if addons and not selected:raise APIError('Stay extras require a villa reservation.')
 a,b=dates(v.get('checkin'),v.get('checkout')) if selected else (None,None); nights=(b-a).days if selected else 0
 rooms={r['id']:r for r in get(c,'rooms')};extras={r['id']:r for r in get(c,'addons')}
 booked=holding(c); lines=[]; supplementary=[]; seen=set()
 for item in selected:
  if not isinstance(item,dict):raise APIError('Invalid villa selection.')
  rid=ident(item.get('id'));r=rooms.get(rid)
  if rid in seen or not r or not enabled(r):raise APIError('A selected villa is not currently bookable.')
  seen.add(rid);qty=integer(item.get('qty'),1,30);guests=integer(item.get('guests'),1,r['capacity']*qty)
  for day in range(nights):
   night=(a+timedelta(days=day)).isoformat();occupied=sum(l['qty'] for p in booked if p.get('checkin') and p['checkin']<=night<p['checkout'] for l in p['rooms'] if l['id']==rid)
   if occupied+qty>r['inventory']:raise APIError(f"Not enough availability for {r['name']} on {night}.",409)
  lines.append({'id':rid,'name':r['name'],'qty':qty,'guests':guests,'unit':r['price'],'total':r['price']*qty*nights})
 seen=set()
 for item in addons:
  if not isinstance(item,dict):raise APIError('Invalid extra.')
  eid=ident(item.get('id'));e=extras.get(eid)
  if eid in seen or not e or not e.get('active') or e['price'] is None:raise APIError('An extra is no longer available.')
  seen.add(eid);qty=integer(item.get('qty'),1,99);supplementary.append({'id':eid,'name':e['name'],'qty':qty,'unit':e['price'],'total':e['price']*qty*(nights if e['basis']=='night' else 1),'basis':e['basis']})
 service_lines=[]; offerings={r['id']:r for r in get(c,'services')}; seen=set(); daily={}
 for item in services:
  if not isinstance(item,dict):raise APIError('Invalid service selection.')
  sid=ident(item.get('id')); r=offerings.get(sid)
  if not r or not service_enabled(r):raise APIError('A selected event or dining option is not currently bookable.')
  try:day=date.fromisoformat(item.get('date'))
  except (ValueError,TypeError):raise APIError('Choose a valid reservation date.')
  if day<today() or day>today()+timedelta(days=730):raise APIError('Choose a future reservation date.')
  when=clean(item.get('time',''),5,True)
  if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',when):raise APIError('Choose a valid time.')
  if datetime.combine(day,datetime.strptime(when,'%H:%M').time(),tzinfo=timezone(timedelta(hours=8)))<=datetime.now(timezone(timedelta(hours=8))):raise APIError('Choose a future reservation time.')
  key=(sid,day.isoformat(),when)
  if key in seen:raise APIError('Duplicate service reservation.')
  seen.add(key); guests=integer(item.get('guests'),1,r['capacity']); occasion=clean(item.get('occasion',''),150,r['kind']=='event')
  # Conservative day-wide inventory: one event across the resort per day; dining seats shared across all times at each venue.
  group=('event' if r['kind']=='event' else sid,day.isoformat()); used=sum((1 if r['kind']=='event' else l['guests']) for p in booked for l in p.get('services',[]) if l['date']==day.isoformat() and (l['kind']=='event' if r['kind']=='event' else l['id']==sid)); units=1 if r['kind']=='event' else guests
  daily[group]=daily.get(group,0)+units
  if used+daily[group]>(1 if r['kind']=='event' else r['capacity']):raise APIError(f"Not enough availability for {r['name']} on {day.isoformat()}.",409)
  service_lines.append({'id':sid,'name':r['name'],'kind':r['kind'],'date':day.isoformat(),'time':when,'guests':guests,'occasion':occasion,'qty':units,'unit':r['price'],'total':r['price']*units})
 total=sum(x['total'] for x in lines+supplementary+service_lines)
 return {'checkin':a.isoformat() if a else None,'checkout':b.isoformat() if b else None,'nights':nights,'rooms':lines,'addons':supplementary,'services':service_lines,'total':total,'currency':'PHP'}

def validate_photo_urls(c,images,max_images=15):
 if not isinstance(images,list) or len(images)>max_images:raise APIError(f'Choose up to {max_images} photos.')
 seed_photos={im for room in SEED['rooms'] for im in room.get('images',[])}
 for url in images:
  if not isinstance(url,str):raise APIError('Invalid photo URL.')
  if url in seed_photos and (PUBLIC/url.lstrip('/')).is_file():continue
  if not re.fullmatch(r'/(?:uploads|api/photo)/[a-f0-9]{32}\.(jpg|png|webp)',url):raise APIError('Upload photos using the dashboard.')
  if not c.execute('SELECT 1 FROM amorap_booking.photos WHERE name=%s',(Path(url).name,)).fetchone():raise APIError('An uploaded photo is missing. Upload it again.')
 return images

def validate_rooms(c,rows):
 if not isinstance(rows,list) or len(rows)>100:raise APIError('Invalid room list.')
 result=[]; ids=set()
 for r in rows:
  if not isinstance(r,dict):raise APIError('Invalid villa.')
  rid=ident(r.get('id'))
  if rid in ids:raise APIError('Duplicate villa ID.')
  ids.add(rid);amen=r.get('amenities',[]);imgs=r.get('images',[])
  if not isinstance(amen,list) or len(amen)>40:raise APIError('Invalid amenities.')
  imgs=validate_photo_urls(c,imgs)
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

def service_enabled(r):return r.get('active') is True and r.get('reviewed') is True and (r.get('price') or 0)>0 and r.get('capacity',0)>0

def validate_services(c,rows):
 if not isinstance(rows,list) or len(rows)>100:raise APIError('Invalid service list.')
 result=[];ids=set()
 for r in rows:
  if not isinstance(r,dict):raise APIError('Invalid service.')
  sid=ident(r.get('id'));kind=r.get('kind')
  if sid in ids or kind not in ('event','dining'):raise APIError('Invalid or duplicate service.')
  imgs=validate_photo_urls(c,r.get('images',[]),12)
  ids.add(sid);result.append({'id':sid,'kind':kind,'name':clean(r.get('name'),120,True),'description':clean(r.get('description',''),3000),'price':amount(r.get('price')),'capacity':integer(r.get('capacity'),0,1000),'images':imgs,'active':r.get('active') is True,'reviewed':r.get('reviewed') is True})
 return result

def fallback_catalog():
 return {'rooms':[{**r,'bookable':False} for r in SEED['rooms'] if r['active']], 'addons':[], 'services':[{**r,'bookable':False} for r in SEED['services'] if r['active']], 'paymentReady':False,'paymentMethods':[],'fallback':True}

def public_catalog(c):
 return {'rooms':[{**r,'bookable':enabled(r)} for r in get(c,'rooms') if r['active']], 'addons':[r for r in get(c,'addons') if r['active'] and r['price'] is not None], 'services':[{**r,'bookable':service_enabled(r)} for r in get(c,'services') if r['active']], 'paymentReady':payment_ready(get(c,'payment')),'paymentMethods':payment_methods(get(c,'payment'))}

def remove_unreferenced_photos(c, images):
 # Only delete actual stored uploads, never bundled resort photos. Keep a
 # photo if it is still used by another villa, event or dining listing.
 if not images:return
 try:
  references={url for section in ('rooms','services') for item in get(c,section) for url in item.get('images',[]) if isinstance(url,str)}
 except Exception:
  # On a damaged catalog, keep the files; do not risk deleting shared photos.
  return
 for url in set(images)-references:
  if re.fullmatch(r'/(?:api/photo|uploads)/[a-f0-9]{32}\.(?:jpg|png|webp)',url):
   c.execute('DELETE FROM amorap_booking.photos WHERE name=%s',(url.rsplit('/',1)[-1],))

def guest(v):
 if not isinstance(v,dict):raise APIError('Enter guest details.')
 out={k:clean(v.get(k,''),n,req) for k,n,req in [('name',150,True),('email',200,True),('phone',70,True),('requests',2000,False)]}
 if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',out['email']):raise APIError('Enter a valid email address.')
 return out

def booking_record(r):
 return {'id':r['id'],'status':r['status'],'created':r['created'],'expires':r['expires'],'reference':r['reference'],**decode_json(r['payload'])}

def dashboard_error(section,e):
 ref=secrets.token_hex(5)
 state=getattr(e,'sqlstate',None)
 frames=' > '.join(f'{Path(f.filename).name}:{f.lineno}:{f.name}' for f in traceback.extract_tb(e.__traceback__)[-5:])
 print(f'AMORAP dashboard {ref}: section={section} {type(e).__name__} SQLSTATE={state} {frames}',flush=True)
 code='DATABASE_SCHEMA_ERROR' if state in ('42P01','42703','3F000') else 'DATABASE_PERMISSION_ERROR' if state=='42501' else 'DATABASE_UNAVAILABLE' if isinstance(e,psycopg.OperationalError) else (e.code if isinstance(e,APIError) and e.code else 'DASHBOARD_SECTION_ERROR')
 text={'DATABASE_SCHEMA_ERROR':'Database structure is incomplete.','DATABASE_PERMISSION_ERROR':'Database access is not configured for this section.','DATABASE_UNAVAILABLE':'Database connection interrupted.','SETTING_INVALID':'Saved settings have an invalid format.','SETTING_MISSING':'A required setting is missing.'}.get(code,'This section could not be loaded.')
 return {'error':f'{text} Reference: {ref}','code':code,'reference':ref}

def admin_section(c,key):
 if key in ('rooms','addons','payment','services'):
  result=get(c,key)
  if key!='payment':
   for row in result:
    if not isinstance(row,dict) or not isinstance(row.get('id'),str):raise APIError('Invalid stored catalog record.',500,'SETTING_INVALID')
    if key=='rooms' and any(not isinstance(row.get(field,[]),list) or any(not isinstance(x,str) for x in row.get(field,[])) for field in ('images','amenities')):raise APIError('Invalid stored villa record.',500,'SETTING_INVALID')
    if key=='services' and (not isinstance(row.get('images',[]),list) or any(not isinstance(x,str) for x in row.get('images',[]))):raise APIError('Invalid stored service photos.',500,'SETTING_INVALID')
  return result
 if key=='bookings':
  expire_holds(c)
  records=[booking_record(r) for r in c.execute('SELECT * FROM amorap_booking.reservations ORDER BY created DESC')]
  for record in records:
   if not isinstance(record.get('guest'),dict) or not isinstance(record.get('payment'),dict) or not isinstance(record.get('status'),str) or any(not isinstance(record.get(field,[]),list) or any(not isinstance(x,dict) for x in record.get(field,[])) for field in ('rooms','addons','services')) or not all(field in record for field in ('rooms','addons')):raise APIError('Invalid stored reservation record.',500,'RESERVATION_FORMAT_ERROR')
  return records
 if key=='messages':return [{'id':r['id'],'created':r['created'],**decode_json(r['payload'])} for r in c.execute('SELECT * FROM amorap_booking.messages ORDER BY created DESC')]
 raise ValueError('Unknown dashboard section')

def dashboard_data(c):
 # Each section has a savepoint: PostgreSQL aborts a transaction on SQL errors
 # until it is rolled back. A broken read cannot poison the remaining reads.
 payload={'revisions':{},'sectionErrors':{},'release':DASHBOARD_RELEASE}
 for key in ('rooms','addons','payment','services','bookings','messages'):
  c.execute('SAVEPOINT admin_section_read')
  try:
   result=admin_section(c,key)
   # Verify JSON compatibility before giving it to the HTTP responder.
   json.dumps(result,ensure_ascii=False,allow_nan=False)
   rev=revision(result) if key in ('rooms','addons','payment','services') else None
   c.execute('RELEASE SAVEPOINT admin_section_read')
  except Exception as e:
   # A lost physical connection cannot be repaired by a savepoint. Let the
   # normal connection error handler respond rather than claiming data loaded.
   c.execute('ROLLBACK TO SAVEPOINT admin_section_read')
   c.execute('RELEASE SAVEPOINT admin_section_read')
   payload['sectionErrors'][key]=dashboard_error(key,e)
   continue
  payload[key]=result
  if rev is not None:payload['revisions'][key]=rev
 return payload

def token_hash(t):return hashlib.sha256(t.encode()).hexdigest()
class Handler(BaseHTTPRequestHandler):
 server_version='Amora/1.0'
 def end_headers(self):
  self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'; object-src 'none'");super().end_headers()
 def respond(self,data,status=200,cookie=None):
  raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)))
  if urlsplit(self.path).path.startswith('/api/admin/'):
   self.send_header('Vary','Cookie');self.send_header('Pragma','no-cache');self.send_header('CDN-Cache-Control','no-store');self.send_header('Surrogate-Control','no-store');self.send_header('X-AMORAP-Admin-Version',ADMIN_VERSION);self.send_header('X-AMORAP-Dashboard-Release',DASHBOARD_RELEASE)
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
  try:t=SimpleCookie(self.headers.get('Cookie',''))[SESSION_COOKIE].value
  except (KeyError,ValueError,CookieError):raise APIError('No admin session cookie received.',401,'SESSION_MISSING')
  if not re.fullmatch(r'[A-Za-z0-9_-]{43}',t):raise APIError('Invalid admin session cookie.',401,'SESSION_INVALID')
  with db(lock=False) as c:
   s=c.execute('SELECT csrf,expiry FROM amorap_booking.admin_sessions WHERE token=%s AND expiry>%s',(token_hash(t),int(time.time()))).fetchone()
  if not s:raise APIError('Your admin session has expired or was signed out.',401,'SESSION_EXPIRED')
  return t,s
 def admin(self,write=False):
  t,s=self.session()
  if write and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']):raise APIError('Invalid session token.',403,'CSRF_INVALID')
  return t,s
 def cookie(self,t,age):
  # HTTPS reverse proxies terminate TLS before forwarding to this server. Only
  # use forwarded protocol to ADD Secure, never to bypass an origin check.
  secure=SECURE or self.headers.get('X-Forwarded-Proto','').split(',')[0].strip().lower()=='https' or self.headers.get('Origin','').startswith('https://') or PUBLIC_ORIGIN.startswith('https://') or hasattr(self.connection,'cipher')
  return f'{SESSION_COOKIE}={t}; Path=/; HttpOnly; SameSite=Lax; Max-Age={age}'+('; Secure' if secure else '')+('' if age else '; Expires=Thu, 01 Jan 1970 00:00:00 GMT')
 def origin(self):
  site=self.headers.get('Sec-Fetch-Site','');org=self.headers.get('Origin','')
  if site in ('cross-site','same-site'):raise APIError('Cross-site request denied.',403,'ORIGIN_DENIED')
  if not org:return
  parsed=urlsplit(org)
  if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:raise APIError('Cross-site request denied.',403,'ORIGIN_DENIED')
  if PUBLIC_ORIGIN:
   if org==PUBLIC_ORIGIN:return
  elif parsed.netloc==self.headers.get('Host') or site=='same-origin':return
  # Browsers set Sec-Fetch-Site themselves; an internal proxy Host may differ
  # from the public origin. For older browsers configure AMORA_PUBLIC_ORIGIN.
  raise APIError('Request origin does not match the configured website. Check the canonical host or reverse proxy.',403,'ORIGIN_DENIED')
 def do_GET(self):self.dispatch('GET')
 def do_HEAD(self):self.dispatch('HEAD')
 def do_POST(self):self.dispatch('POST')
 def do_PUT(self):self.dispatch('PUT')
 def do_DELETE(self):self.dispatch('DELETE')
 def dispatch(self,method):
  path=unquote(urlsplit(self.path).path)
  try:
   if not path.startswith('/api/'):
    if method not in ('GET','HEAD'):raise APIError('Not found.',404)
    return self.static(path)
   if method!='GET':self.origin()
   return self.api(method,path)
  except APIError as e:self.respond({'error':str(e),**({'code':e.code} if e.code else {})},e.status)
  except (BrokenPipeError,ConnectionResetError):pass
  except psycopg.OperationalError:
   print('Database connection unavailable.',flush=True)
   if path=='/api/catalog' and method=='GET':return self.respond(fallback_catalog())
   self.respond({'error':('The admin database is temporarily unavailable. Please retry; a connection failure does not end your session.' if path.startswith('/api/admin/') else 'The reservation service is temporarily unavailable. Please try again later.')},503)
  except Exception as e:
   ref=secrets.token_hex(5)
   # Do not print exception text, query parameters, credentials or customer data.
   frames=' > '.join(f'{Path(f.filename).name}:{f.lineno}:{f.name}' for f in traceback.extract_tb(e.__traceback__)[-6:])
   print(f'AMORAP error {ref}: {method} {path[:100]} {type(e).__name__} SQLSTATE={getattr(e,"sqlstate",None)} {frames}',flush=True)
   if path=='/api/catalog' and method=='GET':return self.respond(fallback_catalog())
   code='DASHBOARD_DATA_ERROR' if path=='/api/admin/data' else 'SERVER_ERROR'
   if getattr(e,'sqlstate',None) in ('42P01','42703','3F000'):code='DATABASE_SCHEMA_ERROR'
   msg=('Hotel database setup is incomplete. Apply the AMORAP dashboard repair SQL.' if code=='DATABASE_SCHEMA_ERROR' else 'Dashboard data could not be loaded. Contact support with the error reference.' if code=='DASHBOARD_DATA_ERROR' else 'An unexpected server error occurred.')
   self.respond({'error':f'{msg} Reference: {ref}','code':code,'reference':ref},500)
 def serve_photo(self,name):
  # Keep legacy /uploads links working, but use /api/photo for new uploads so
  # Vercel configurations that route /api/* to Python also serve the image.
  if not re.fullmatch(r'[a-f0-9]{32}\.(jpg|png|webp)',name):raise APIError('Not found.',404)
  with db(lock=False) as c:
   photo=c.execute('SELECT content,mime FROM amorap_booking.photos WHERE name=%s',(name,)).fetchone()
  if not photo:raise APIError('Not found.',404)
  raw=bytes(photo['content']);self.send_response(200);self.send_header('Content-Type',photo['mime']);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','public, max-age=300');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();
  if self.command!='HEAD':self.wfile.write(raw)
 def static(self,path):
  if path.startswith('/uploads/'):
   return self.serve_photo(path.split('/')[-1])
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
  self.send_response(206 if partial else 200);self.send_header('Content-Type',mime+('; charset=utf-8' if mime.startswith('text/') else ''));self.send_header('Content-Length',str(end-start+1));self.send_header('Cache-Control','no-store' if mime=='text/html' or f.name=='admin.js' else 'public, max-age=300')
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
  if path.startswith('/api/photo/') and method=='GET':return self.serve_photo(path.split('/')[-1])
  if PREVIEW:
   if path=='/api/catalog' and method=='GET':return self.respond({'rooms':[{**r,'bookable':False} for r in SEED['rooms'] if r['active']],'addons':[],'services':[{**r,'bookable':False} for r in SEED['services'] if r['active']],'paymentReady':False,'paymentMethods':[],'preview':True})
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
   with db(lock=False) as c:
    c.execute('DELETE FROM amorap_booking.admin_sessions WHERE expiry<=%s',(int(now),))
    c.execute('INSERT INTO amorap_booking.admin_sessions (token,csrf,expiry) VALUES (%s,%s,%s)',(token_hash(t),csrf,int(now)+SESSION_SECONDS))
   with LOCK:ATTEMPTS.pop(ip,None)
   return self.respond({'csrf':csrf,'expiresAt':int(now)+SESSION_SECONDS,'version':ADMIN_VERSION},cookie=self.cookie(t,SESSION_SECONDS))
  if path.startswith('/api/admin/'):
   t,s=self.admin(method!='GET')
   if path=='/api/admin/session' and method=='GET':
    now=int(time.time());expiry=s['expiry'];cookie=None
    if expiry<=now+SESSION_SECONDS-SESSION_RENEW_AFTER:
     with db(lock=False) as c:
      renewed=c.execute('UPDATE amorap_booking.admin_sessions SET expiry=%s WHERE token=%s AND expiry>%s RETURNING expiry',(now+SESSION_SECONDS,token_hash(t),now)).fetchone()
     if not renewed:raise APIError('Your admin session has expired or was signed out.',401,'SESSION_EXPIRED')
     expiry=renewed['expiry'];cookie=self.cookie(t,SESSION_SECONDS)
    return self.respond({'csrf':s['csrf'],'expiresAt':expiry,'version':ADMIN_VERSION},cookie=cookie)
   if path=='/api/admin/logout' and method=='POST':
    with db(lock=False) as c:c.execute('DELETE FROM amorap_booking.admin_sessions WHERE token=%s',(token_hash(t),))
    return self.respond({'ok':True},cookie=self.cookie('',0))
   if path=='/api/admin/upload' and method=='POST':
    v=self.body();data=v.get('data','')
    if not isinstance(data,str):raise APIError('Invalid photo.')
    try:raw=base64.b64decode(data,validate=True)
    except Exception:raise APIError('Invalid photo.')
    if not raw or len(raw)>2_000_000:raise APIError('Photo is too large. Choose another photo or allow the browser to optimize it (2 MB maximum).',413)
    ext='jpg' if raw.startswith(b'\xff\xd8\xff') else 'png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'webp' if raw[:4]==b'RIFF' and raw[8:12]==b'WEBP' else None
    if not ext:raise APIError('Choose a JPEG, PNG or WebP photo.')
    name=secrets.token_hex(16)+'.'+ext
    mime={'jpg':'image/jpeg','png':'image/png','webp':'image/webp'}[ext]
    with db() as c:c.execute('INSERT INTO amorap_booking.photos (name,mime,content) VALUES (%s,%s,%s)',(name,mime,raw))
    return self.respond({'url':'/api/photo/'+name})
   with db() as c:
    if path=='/api/admin/discard-photo' and method=='DELETE':
     # A freshly uploaded picture may be removed before a catalog Save.
     # Never remove any image already used by a saved villa or service.
     url=self.body().get('url')
     if not isinstance(url,str) or not re.fullmatch(r'/api/photo/[a-f0-9]{32}\.(?:jpg|png|webp)',url):raise APIError('Only new dashboard uploads can be discarded.')
     if any(url in item.get('images',[]) for key in ('rooms','services') for item in get(c,key)):
      raise APIError('This picture is already published. Use Delete photo on the listing.',409)
     c.execute('DELETE FROM amorap_booking.photos WHERE name=%s',(url.rsplit('/',1)[-1],))
     c.commit()
     return self.respond({'ok':True})
    if path in ('/api/admin/delete-item','/api/admin/delete-photo') and method=='DELETE':
     v=self.body();section=v.get('section')
     allowed=('rooms','services','addons') if path.endswith('delete-item') else ('rooms','services')
     if section not in allowed:raise APIError('Invalid catalog section.')
     rid=ident(v.get('id'));items=get(c,section)
     expected=self.headers.get('If-Match')
     if not expected:raise APIError('Refresh your dashboard before deleting. Missing revision.',428)
     if expected!=revision(items):raise APIError('Someone changed this section. Refresh before deleting; no changes were made.',409)
     target=next((item for item in items if item.get('id')==rid),None)
     if target is None:raise APIError('This item no longer exists. Refresh the dashboard.',404)
     removed=[]
     if path.endswith('delete-item'):
      updated=[item for item in items if item.get('id')!=rid]
      removed=list(target.get('images',[]))
     else:
      url=v.get('url')
      if not isinstance(url,str) or url not in target.get('images',[]):raise APIError('Photo not found in this listing. Refresh and retry.',404)
      updated=[{**item,'images':[im for im in item['images'] if im!=url]} if item.get('id')==rid else item for item in items]
      removed=[url]
     save(c,section,updated)
     remove_unreferenced_photos(c,removed)
     c.commit()
     return self.respond({'ok':True,'value':updated,'revision':revision(updated)})
    if path=='/api/admin/data' and method=='GET':
     payload=dashboard_data(c);c.commit();return self.respond(payload)
    if path in ('/api/admin/rooms','/api/admin/addons','/api/admin/payment','/api/admin/services') and method=='PUT':
     v=self.body();key=path.rsplit('/',1)[1]
     expected=self.headers.get('If-Match')
     current=get(c,key)
     if expected and expected!=revision(current):raise APIError('Another administrator changed these settings. Your edits are still here. Copy them if needed, then refresh before saving.',409)
     if key=='rooms':val=validate_rooms(c,v.get('items'))
     elif key=='addons':val=validate_addons(v.get('items'))
     elif key=='services':val=validate_services(c,v.get('items'))
     else:val=validate_payment(v,current)
     save(c,key,val);c.commit();return self.respond({'ok':True,'value':val,'revision':revision(val)})
    if path=='/api/admin/status' and method=='POST':
     v=self.body();rid=ident(v.get('id'));status=v.get('status'); holding(c)
     r=c.execute('SELECT * FROM amorap_booking.reservations WHERE id=%s',(rid,)).fetchone()
     if not r:raise APIError('Reservation not found.',404)
     transitions={'awaiting_payment':('confirmed','cancelled'),'payment_review':('confirmed','cancelled'),'confirmed':('cancelled',),'expired':(),'cancelled':()}
     if status not in transitions.get(r['status'],()):raise APIError('This status change is not permitted.')
     c.execute('UPDATE amorap_booking.reservations SET status=%s WHERE id=%s',(status,rid));c.commit();return self.respond({'ok':True,'booking':booking_record({**r,'status':status})})
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
    rid='AM-'+secrets.token_hex(5).upper();token=secrets.token_urlsafe(32);now=int(time.time());payload={**q,'guest':person,'payment':payment_snapshot(p,v.get('paymentMethod'))}
    expires=min([now+HOLD_SECONDS]+[int(datetime.fromisoformat(l['date']+'T'+l['time']+':00+08:00').timestamp()) for l in q['services']])
    if expires<=now:raise APIError('Choose a future reservation time.')
    c.execute('INSERT INTO amorap_booking.reservations (id,token,status,created,expires,payload,reference) VALUES(%s,%s,%s,%s,%s,%s,%s)',(rid,token_hash(token),'awaiting_payment',now,expires,json.dumps(payload,ensure_ascii=False),''));c.commit()
    return self.respond({'booking':{'id':rid,'status':'awaiting_payment','expires':expires,**payload},'token':token},201)
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
