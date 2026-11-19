"""End-to-end service photo QA, local SQLite test adapter; no live Supabase data touched."""
import base64, tempfile, threading, sys, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_admin import TestDB,Client,server,ROOT

with tempfile.TemporaryDirectory() as tmp:
 db=TestDB(str(Path(tmp)/'qa.sqlite'));db.setup();server.db=db.connect;server.USER='qa-admin';server.PASSWORD='QA-only-test-password-123';server.PREVIEW=False
 class Quiet(server.Handler):
  def log_message(self,*args):pass
 h=server.ThreadingHTTPServer(('127.0.0.1',0),Quiet);t=threading.Thread(target=h.serve_forever,daemon=True);t.start()
 try:
  a=Client(h.server_port);a.login();u=Client(h.server_port)
  photo=(ROOT/'public/assets/villas/inland-resort.webp').read_bytes()
  url=a.send('POST','/api/admin/upload',{'data':base64.b64encode(photo).decode()})['url']
  assert u.send('GET',url)==photo
  saved=a.get();services=saved['services']
  assert not services[0].get('images') # no migration required for old records
  services[0]['images']=[url]
  services[1]['images']=[url]
  s=a.save('services',{'items':services},saved['revisions']['services'])
  catalog=u.send('GET','/api/catalog');assert catalog['services'][0]['images']==[url] and catalog['services'][1]['images']==[url]
  assert a.get()['services'][0]['images']==[url]
  services[0]['images']=[];s=a.save('services',{'items':services},s['revision']);assert u.send('GET','/api/catalog')['services'][0]['images']==[]
  services[0]['images']=['https://example.com/foreign.jpg'];a.save('services',{'items':services},s['revision'],400)
  services[0]['images']=[url,'/uploads/00000000000000000000000000000000.png'];a.save('services',{'items':services},s['revision'],400)
  a.send('POST','/api/admin/upload',{'data':base64.b64encode(b'\xff\xd8\xff'+b'\x00'*2_000_000).decode()},413)
  u.send('POST','/api/admin/upload',{'data':base64.b64encode(photo).decode()},401)
  print('PASS: authenticated upload, public images, event/dining save, gallery remove, invalid URL rejected, oversized uploads rejected')
 finally:h.shutdown();h.server_close()
