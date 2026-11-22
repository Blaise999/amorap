"""Regression: authenticated serverless-style imports with old catalog rows.
Uses isolated SQLite adapter; no production credentials or data.
"""
import copy, json, tempfile, threading
from pathlib import Path
from qa_admin import TestDB, Client, server

def run(port, db):
    # Simulate older schema state on a host that imports server without init().
    rooms=copy.deepcopy(server.SEED['rooms']);rooms[0]['name']='Existing owner edit';rooms[0]['price']=123456
    payment={'bank':'Existing bank','name':'Test owner','number':'000','instructions':'Test'}
    with db.connect() as c:
        c.execute('DELETE FROM settings WHERE key=%s',('services',))
        c.execute('UPDATE settings SET value=%s WHERE key=%s',(json.dumps(rooms),'rooms'))
        c.execute('UPDATE settings SET value=%s WHERE key=%s',(json.dumps(payment),'payment'))
        c.execute('UPDATE settings SET value=%s WHERE key=%s',('[]','addons'))
    a=Client(port);a.login();assert a.get('session')['csrf']==a.csrf
    d=a.get();assert d['rooms']==rooms and d['payment']==payment and d['addons']==[] and d['services']==server.SEED['services']
    with db.connect() as c:assert json.loads(c.execute('SELECT value FROM settings WHERE key=%s',('services',)).fetchone()['value'])==server.SEED['services']
    d['services'][0]['name']='Owner event edit';saved=a.save('services',{'items':d['services']},d['revisions']['services']);assert saved['ok']
    assert a.get()['services'][0]['name']=='Owner event edit';assert Client(port).send('GET','/api/catalog')['services'][0]['name']=='Owner event edit'
    print('PASS missing services repaired after login; owner edits, bank details and intentionally empty extras preserved; services save publicly visible')
    # Missing settings before initial full dashboard request, including PUT with no revision.
    with db.connect() as c:c.execute('DELETE FROM settings WHERE key=%s',('payment',))
    assert a.save('payment',payment)['ok'];assert all(a.get()['payment'].get(k)==v for k,v in payment.items())
    # Invalid existing data is not silently reset or mistaken for an expired session.
    with db.connect() as c:c.execute('UPDATE settings SET value=%s WHERE key=%s',('not-json','services'))
    d=a.get();assert d['sectionErrors']['services']['code']=='SETTING_INVALID' and 'services' not in d and 'services' not in d['revisions'];assert d['rooms']==rooms and all(d['payment'].get(k)==v for k,v in payment.items());assert a.get('session')['csrf']==a.csrf
    assert a.save('payment',{**payment,'instructions':'Still editable'},d['revisions']['payment'])['ok']
    with db.connect() as c:
        assert c.execute('SELECT value FROM settings WHERE key=%s',('services',)).fetchone()['value']=='not-json'
        c.execute('UPDATE settings SET value=%s WHERE key=%s',(json.dumps(saved['value']),'services'))
        c.execute('DROP TABLE messages')
    d=a.get();err=d['sectionErrors']['messages'];assert err['reference'] and 'messages' not in d and not d['sectionErrors'].get('rooms');assert a.get('session')['csrf']==a.csrf
    assert d['payment']['instructions']=='Still editable' and d['services'][0]['name']=='Owner event edit'
    with db.connect() as c:
        c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT,created INT,payload TEXT)')
        c.execute('INSERT INTO messages(created,payload) VALUES(%s,%s)',(123,'null'))
    d=a.get();assert 'messages' not in d and d['sectionErrors']['messages']['reference'];assert d['bookings']==[]
    with db.connect() as c:c.execute('DELETE FROM messages')
    d=a.get();assert d['messages']==[] and d['sectionErrors']=={}
    assert d['release']==server.DASHBOARD_RELEASE
    print('PASS malformed settings preserved, session stays active, unexpected data errors return support reference')
    assert server.decode_json({'k':1})=={'k':1};assert server.decode_json('[1]')==[1]

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as tmp:
        db=TestDB(str(Path(tmp)/'qa.sqlite'));db.setup();server.db=db.connect
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        h=server.ThreadingHTTPServer(('127.0.0.1',0),Quiet);t=threading.Thread(target=h.serve_forever,daemon=True);t.start()
        try:run(h.server_port,db)
        finally:h.shutdown();h.server_close();t.join()
