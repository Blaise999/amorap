"""Extra guest pricing: admin-configured cents, server-side quotes, capacity and multiple rooms."""
import tempfile,threading,sys
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_admin import server,Client,TestDB
with tempfile.TemporaryDirectory() as tmp:
 db=TestDB(str(Path(tmp)/'extra_guest.sqlite'));db.setup();server.db=db.connect
 class Quiet(server.Handler):
  def log_message(self,*args):pass
 web=server.ThreadingHTTPServer(('127.0.0.1',0),Quiet)
 threading.Thread(target=web.serve_forever,daemon=True).start()
 try:
  admin=Client(web.server_port);guest=Client(web.server_port);admin.login()
  d=admin.get();rooms=d['rooms'];r=rooms[0]
  r.update(capacity=8,inventory=3,price=500000,extraGuestFee=75000,reviewed=True,active=True)
  admin.save('rooms',{'items':rooms},d['revisions']['rooms'])
  public=guest.send('GET','/api/catalog')['rooms'][0]
  assert public['includedGuests']==5 and public['extraGuestFee']==75000
  start=server.today()+timedelta(days=4);end=start+timedelta(days=2)
  def quote(people,qty=1,expected=200):
   return guest.send('POST','/api/quote',{'checkin':start.isoformat(),'checkout':end.isoformat(),'rooms':[{'id':r['id'],'qty':qty,'guests':people,'extraGuestFee':0}],'addons':[],'services':[]},expected)
  assert quote(5)['total']==1000000
  extra=quote(6);assert extra['total']==1150000 and extra['rooms'][0]['extraGuestTotal']==150000
  assert quote(8)['total']==1450000
  quote(9,expected=400)
  assert quote(10,2)['total']==2000000
  assert quote(12,2)['total']==2300000
  d=admin.get();rooms=d['rooms'];rooms[0]['extraGuestFee']=100000
  admin.save('rooms',{'items':rooms},d['revisions']['rooms'])
  assert quote(6)['total']==1200000
  d=admin.get();rooms=d['rooms'];rooms[0]['extraGuestFee']=0
  admin.save('rooms',{'items':rooms},d['revisions']['rooms'])
  quote(6,expected=409)
  d=admin.get();rooms=d['rooms'];rooms[0].update(capacity=3,extraGuestFee=100000,petsAllowed=True,maxPets=3,petFee=25000)
  admin.save('rooms',{'items':rooms},d['revisions']['rooms'])
  public=guest.send('GET','/api/catalog')['rooms'][0]
  assert public['includedGuests']==3 and public['maxExtraGuests']==3 and public['capacity']==6
  assert quote(5)['total']==1400000
  d=admin.get();rooms=d['rooms'];rooms[0]['maxExtraGuests']=2
  admin.save('rooms',{'items':rooms},d['revisions']['rooms'])
  assert quote(5)['total']==1400000
  quote(6,expected=400)
  combined=guest.send('POST','/api/quote',{'checkin':start.isoformat(),'checkout':end.isoformat(),'rooms':[{'id':r['id'],'qty':1,'guests':5,'pets':2}],'addons':[],'services':[]},200)
  assert combined['total']==1450000 and combined['rooms'][0]['petTotal']==50000
  print('PASS extra guests, three included, independent limits, pets and server-authoritative pricing')
 finally:
  web.shutdown();web.server_close()
