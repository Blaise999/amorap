"""Room inventory and date-scoped availability regression (isolated SQLite only)."""
import json,threading,tempfile,sys
from datetime import timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_admin import server,Client,TestDB

with tempfile.TemporaryDirectory() as tmp:
 db=TestDB(str(Path(tmp)/'room_stock.sqlite'));db.setup();server.db=db.connect
 class Quiet(server.Handler):
  def log_message(self,*args):pass
 web=server.ThreadingHTTPServer(('127.0.0.1',0),Quiet)
 thread=threading.Thread(target=web.serve_forever,daemon=True);thread.start()
 try:
  admin=Client(web.server_port);guest=Client(web.server_port);admin.login()
  dashboard=admin.get()
  rooms=dashboard['rooms']
  assert len(rooms)==4,rooms
  for r,count in zip(rooms,[3,5,2,0]):
   r.update(inventory=count,reviewed=True,active=True)
  saved=admin.save('rooms',{'items':rooms},dashboard['revisions']['rooms'])
  assert [r['inventory'] for r in saved['value']]==[3,5,2,0]
  catalog=guest.send('GET','/api/catalog')
  assert [r['inventory'] for r in catalog['rooms']]==[3,5,2,0]
  assert catalog['rooms'][3]['bookable'] is False
  start=server.today()+timedelta(days=4);end=start+timedelta(days=3)
  def availability(a=start,b=end):
   return guest.send('GET','/api/availability?checkin='+a.isoformat()+'&checkout='+b.isoformat())
  initial=availability()
  assert initial['checkin']==start.isoformat() and initial['checkout']==end.isoformat()
  assert [r['available'] for r in initial['rooms']]==[3,5,2,0],initial
  assert initial['rooms'][3]['bookable'] is False
  guest.send('GET','/api/availability?checkin=bad&checkout='+end.isoformat(),expected=400)
  guest.send('GET','/api/availability?checkin='+start.isoformat()+'&checkout='+end.isoformat()+'&checkin='+start.isoformat(),expected=400)

  # A previously confirmed booking occupies two rooms on the middle night.
  overlaps={'checkin':(start+timedelta(days=1)).isoformat(),
            'checkout':(start+timedelta(days=2)).isoformat(),
            'rooms':[{'id':rooms[0]['id'],'qty':2}], 'services':[],'addons':[]}
  with db.connect() as c:
   for status,ref,payload in [('confirmed','stock-confirmed',overlaps),
                              ('awaiting_payment','stock-unpaid',{**overlaps,'rooms':[{'id':rooms[0]['id'],'qty':1}]}),
                              ('payment_review','stock-receipt',{**overlaps,'rooms':[{'id':rooms[0]['id'],'qty':1}]})]:
    c.execute('INSERT INTO amorap_booking.reservations(id,token,status,created,expires,payload,reference) VALUES(%s,%s,%s,%s,%s,%s,%s)',
              (ref,'dummy',status,1000,0,json.dumps(payload),''))
  available=availability()
  assert [r['available'] for r in available['rooms']]==[1,5,2,0],available
  assert availability(start+timedelta(days=2),end+timedelta(days=1))['rooms'][0]['available']==3
  assert 'guest' not in str(available).lower() and 'email' not in str(available).lower()

  quote_base={'checkin':start.isoformat(),'checkout':end.isoformat(),'addons':[],'services':[]}
  def quote(qty,expected=200):
   return guest.send('POST','/api/quote',{**quote_base,'rooms':[{'id':rooms[0]['id'],'qty':qty,'guests':qty}]},expected)
  quote(2,409);quote(1)
  # Reconfiguring total stock must change both the public counts and quote rules.
  dashboard=admin.get();current=dashboard['rooms'];current[0]['inventory']=4
  admin.save('rooms',{'items':current},dashboard['revisions']['rooms'])
  assert guest.send('GET','/api/catalog')['rooms'][0]['inventory']==4
  assert availability()['rooms'][0]['available']==2
  quote(3,409);quote(2)
  with db.connect() as c:
   c.execute("UPDATE amorap_booking.reservations SET status='cancelled' WHERE id=%s",('stock-confirmed',))
  assert availability()['rooms'][0]['available']==4
  quote(3)
  print('PASS admin room quantity save, public inventory visibility, date-scoped remaining stock, sold-out rooms')
  print('PASS pending bookings do not hold rooms; confirmed overlapping stays reduce stock; cancellations restore it')
  print('PASS selected-date quantity validation uses same server calculation; no personal data exposed')
 finally:
  web.shutdown();web.server_close()
