"""Run locally: python tests/qa_delete_now.py. Tests deletion through actual HTTP routes using isolated SQLite adapter."""
import sys, copy, base64, tempfile, threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_admin import TestDB,Client,server,ROOT

with tempfile.TemporaryDirectory() as d:
 db=TestDB(str(Path(d)/'qa.sqlite'));db.setup();server.db=db.connect
 server.USER='qa-admin';server.PASSWORD='QA-only-test-password-123';server.PREVIEW=False
 class Quiet(server.Handler):
  def log_message(self,*args):pass
 h=server.ThreadingHTTPServer(('127.0.0.1',0),Quiet)
 t=threading.Thread(target=h.serve_forever,daemon=True);t.start()
 try:
  a=Client(h.server_port);guest=Client(h.server_port);other=Client(h.server_port)
  a.login();other.login()
  pic=(ROOT/'public/assets/villas/inland-resort.webp').read_bytes()
  url=a.send('POST','/api/admin/upload',{'data':base64.b64encode(pic).decode()})['url']
  before=a.get();v=copy.deepcopy(before['rooms'][0]);v.update(id='qa-delete-villa',name='Delete QA test villa',images=[url],active=True,reviewed=True,capacity=2,inventory=1,price=80000)
  rows=[*before['rooms'],v];saved=a.save('rooms',{'items':rows},before['revisions']['rooms'])
  assert guest.send('GET',url)==pic
  assert any(r['id']==v['id'] for r in guest.send('GET','/api/catalog')['rooms'])
  print('PASS add villa, upload photo, save to catalog, public image GET')
  # A simultaneous update invalidates a stale deletion revision.
  old_revision=before['revisions']['rooms']
  a.send('DELETE','/api/admin/delete-photo',{'section':'rooms','id':v['id'],'url':url},409,old_revision)
  a.send('DELETE','/api/admin/delete-item',{'section':'rooms','id':v['id']},409,old_revision)
  a.send('DELETE','/api/admin/delete-item',{'section':'rooms','id':v['id']},403,saved['revision'],csrf=False)
  guest.send('DELETE','/api/admin/delete-item',{'section':'rooms','id':v['id']},401,saved['revision'])
  a.send('DELETE','/api/admin/delete-item',{'section':'bookings','id':v['id']},400,saved['revision'])
  assert any(r['id']==v['id'] for r in guest.send('GET','/api/catalog')['rooms'])
  print('PASS revision conflicts, CSRF, authentication, blocked reservation deletion')
  # A single image can be linked to multiple records; deleting one reference must not remove the blob.
  records=a.get();services=records['services'];services[0]['images']=[url]
  a.save('services',{'items':services},records['revisions']['services'])
  removed=a.send('DELETE','/api/admin/delete-photo',{'section':'rooms','id':v['id'],'url':url},200,saved['revision'])
  assert next(r for r in removed['value'] if r['id']==v['id'])['images']==[]
  assert guest.send('GET',url)==pic, 'Shared upload must remain available'
  assert next(r for r in guest.send('GET','/api/catalog')['rooms'] if r['id']==v['id'])['images']==[]
  print('PASS instant photo deletion from villa, shared uploaded image preserved')
  now=a.get();sv=now['services'][0]
  a.send('DELETE','/api/admin/delete-photo',{'section':'services','id':sv['id'],'url':url},200,now['revisions']['services'])
  guest.send('GET',url,expected=404)
  assert not next(r for r in guest.send('GET','/api/catalog')['services'] if r['id']==sv['id']).get('images')
  print('PASS last photo reference removed, uploaded image bytes actually deleted')
  deleted=a.send('DELETE','/api/admin/delete-item',{'section':'rooms','id':v['id']},200,removed['revision'])
  assert not any(r['id']==v['id'] for r in deleted['value'])
  assert not any(r['id']==v['id'] for r in guest.send('GET','/api/catalog')['rooms'])
  assert a.get()['revisions']['rooms']==deleted['revision']
  a.send('DELETE','/api/admin/delete-item',{'section':'rooms','id':v['id']},404,deleted['revision'])
  print('PASS instant room deletion persisted, not listed publicly, repeated deletion safely rejected')
  # Service listing and extras can also be deleted without touching reservations.
  current=a.get();service_id=current['services'][0]['id']
  r=a.send('DELETE','/api/admin/delete-item',{'section':'services','id':service_id},200,current['revisions']['services'])
  assert not any(x['id']==service_id for x in guest.send('GET','/api/catalog')['services'])
  current=a.get();extra_id=current['addons'][0]['id']
  a.send('DELETE','/api/admin/delete-item',{'section':'addons','id':extra_id},200,current['revisions']['addons'])
  assert not any(x['id']==extra_id for x in a.get()['addons'])
  print('PASS event/dining and extras immediate delete persisted')
  new_url=a.send('POST','/api/admin/upload',{'data':base64.b64encode(pic).decode()})['url']
  a.send('DELETE','/api/admin/discard-photo',{'url':new_url})
  guest.send('GET',new_url,expected=404)
  a.send('DELETE','/api/admin/discard-photo',{'url':'/assets/villas/inland-resort.webp'},400)
  print('PASS unsaved photo discarded from database; bundled photos protected')
  assert a.get('session')['csrf']==a.csrf
  print('PASS admin session remains active after deletion')
 finally:h.shutdown();h.server_close()
