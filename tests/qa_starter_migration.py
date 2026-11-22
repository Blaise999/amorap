"""Regression: old Supabase villa settings lack starter rates under serverless."""
from qa_admin import server,TestDB
import tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as tmp:
 db=TestDB(str(Path(tmp)/'migration.sqlite'))
 db.setup()
 server.db=db.connect
 with db.connect() as c:
  rows=server.get(c,'rooms')
  for room in rows:room.update(price=None,capacity=0,inventory=0,reviewed=False)
  server.save(c,'rooms',rows)
 with db.connect() as c:
  catalog=server.public_catalog(c)
  assert all(room['price']>0 and room['capacity']>0 and room['inventory']>0 for room in catalog['rooms'])
  assert not any(room['bookable'] for room in catalog['rooms'])
 with db.connect() as c:
  rows=server.get(c,'rooms')
  rows[0]['price']=123456
  server.save(c,'rooms',rows)
 with db.connect() as c:
  assert server.public_catalog(c)['rooms'][0]['price']==123456
 print('PASS one-time starter rates, existing edits preserved, unreviewed rooms disabled')
