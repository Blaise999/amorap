"""End-to-end isolated HTTP checks: children, pets and customer care."""
import tempfile,threading,datetime
from pathlib import Path
from qa_admin import server,Client,TestDB

with tempfile.TemporaryDirectory() as tmp:
 db=TestDB(str(Path(tmp)/'familycare.sqlite'));db.setup();server.db=db.connect
 class Quiet(server.Handler):
  def log_message(self,*args):pass
 web=server.ThreadingHTTPServer(('127.0.0.1',0),Quiet)
 thread=threading.Thread(target=web.serve_forever,daemon=True);thread.start()
 try:
  admin=Client(web.server_port);guest=Client(web.server_port)
  admin.login()
  dashboard=admin.get()
  assert dashboard['support']['phone']==''
  catalog=guest.send('GET','/api/catalog')
  assert catalog['support']['phone']==''
  assert [r['maxKids'] for r in catalog['rooms']]==[2,4,2,4]
  assert all(r['freeChildUnderAge']==12 and not r['petsAllowed'] for r in catalog['rooms'])
  rooms=dashboard['rooms']
  for r in rooms:r.update(reviewed=True,active=True)
  saved=admin.save('rooms',{'items':rooms},dashboard['revisions']['rooms'])
  assert saved['value'][0]['maxKids']==2
  start=server.today()+datetime.timedelta(days=3);end=start+datetime.timedelta(days=2)
  base={'checkin':start.isoformat(),'checkout':end.isoformat(),'addons':[],'services':[]}
  def quote(idx,**kw):
   return guest.send('POST','/api/quote',{**base,'rooms':[{'id':rooms[idx]['id'],'qty':1,'guests':2,**kw}]})
  q=quote(0,kids=2)
  assert q['rooms'][0]['kids']==2 and q['rooms'][0]['petTotal']==0
  assert q['total']==rooms[0]['price']*2
  guest.send('POST','/api/quote',{**base,'rooms':[{'id':rooms[0]['id'],'qty':1,'guests':2,'kids':3}]},400)
  assert quote(1,kids=4)['rooms'][0]['kids']==4
  guest.send('POST','/api/quote',{**base,'rooms':[{'id':rooms[1]['id'],'qty':1,'guests':2,'kids':5}]},400)
  guest.send('POST','/api/quote',{**base,'rooms':[{'id':rooms[0]['id'],'qty':1,'guests':2,'pets':1}]},400)
  revision=saved['revision'];rooms=saved['value']
  rooms[0].update(petsAllowed=True,maxPets=2,petFee=35000,petPolicy='House-trained pets only')
  rooms[1].update(freeChildUnderAge=10,maxKids=5)
  saved=admin.save('rooms',{'items':rooms},revision)
  q=quote(0,kids=2,pets=2)
  assert q['rooms'][0]['petTotal']==70000 and q['total']==rooms[0]['price']*2+70000
  guest.send('POST','/api/quote',{**base,'rooms':[{'id':rooms[0]['id'],'qty':1,'guests':2,'pets':3}]},400)
  assert guest.send('GET','/api/catalog')['rooms'][1]['freeChildUnderAge']==10
  admin.save('support',{'phone':'javascript:alert(1)','email':''},dashboard['revisions']['support'],400)
  support={'phone':'+63 912 345 6789','email':'care@example.test','hours':'Every day, 8am-8pm','greeting':'How can we help?'}
  admin.save('support',support,dashboard['revisions']['support'])
  assert guest.send('GET','/api/catalog')['support']==support
  guest.send('POST','/api/contact',{'name':'QA Customer','email':'customer@example.test','phone':'+63 912 345 6789','message':'Can I bring my dog?'},201)
  msg=admin.get()['messages'][0]
  assert msg['phone']==support['phone'] and 'dog' in msg['message']
  guest.send('POST','/api/contact',{'name':'QA Customer','email':'customer@example.test','phone':'javascript:alert(1)','message':'test'},400)
  admin.save('payment',{'method':'bank','bank':'QA bank','name':'QA person','number':'00000'},admin.get()['revisions']['payment'])
  payload={**base,'rooms':[{'id':rooms[0]['id'],'qty':1,'guests':2,'kids':2,'pets':2}],
   'guest':{'name':'QA Traveller','email':'qa@example.test','phone':'000'},'paymentMethod':'bank','paymentPercent':50}
  booking=guest.send('POST','/api/bookings',payload,201)['booking']
  assert booking['rooms'][0]['kids']==2 and booking['rooms'][0]['pets']==2
  assert booking['total']==q['total'] and booking['dueNow']==(booking['total']+1)//2
  print('PASS default 1BR/2BR limits, under-12 free, configurable age/pets/fees, quotes and reservations')
  print('PASS admin customer care, public phone, guest messages and callback phone validation')
 finally:
  web.shutdown();web.server_close()
