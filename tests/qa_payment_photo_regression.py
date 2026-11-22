"""Regression for Vercel asset isolation and independent GCash/bank settings."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_admin import server,TestDB
import tempfile
with tempfile.TemporaryDirectory() as tmp:
 db=TestDB(str(Path(tmp)/'qa.sqlite'))
 db.setup()
 server.db=db.connect
 old_public=server.PUBLIC
 server.PUBLIC=Path(tmp)/'absent-public'
 try:
  with db.connect() as c:
   before=server.get(c,'rooms')
   assert server.validate_rooms(c,before)[0]['images']==before[0]['images']
   before[0]['images']=['/assets/historical-villa.jpg']
   server.save(c,'rooms',before)
  with db.connect() as c:
   rows=server.get(c,'rooms')
   assert server.validate_rooms(c,rows)[0]['images']==['/assets/historical-villa.jpg']
   rows[0]['images'].append('https://random.example/photo.png')
   try:server.validate_rooms(c,rows)
   except server.APIError:pass
   else:raise AssertionError('Arbitrary new external image URL accepted')
 finally:server.PUBLIC=old_public
 with db.connect() as c:
  bank=server.validate_payment({'method':'bank','bank':'Test bank','name':'QA','number':'00000'},server.get(c,'payment'))
  assert server.payment_methods(bank)==['bank']
  both=server.validate_payment({'method':'gcash','gcashName':'QA wallet','gcashNumber':'639123456789'},bank)
  assert set(server.payment_methods(both))=={'bank','gcash'}
  assert both['gcashNumber']=='+639123456789'
  assert all(both[key]==bank[key] for key in ('bank','name','number'))
  only_bank=server.validate_payment({'method':'gcash','gcashName':'','gcashNumber':''},both)
  assert server.payment_methods(only_bank)==['bank']
  legacy={'bank':'Incomplete','name':'','number':''}
  assert 'gcash' in server.payment_methods(server.validate_payment({'method':'gcash','gcashName':'QA','gcashNumber':'09123456789'},legacy))
print('PASS original and legacy photos on Vercel; independent bank/GCash saves')
