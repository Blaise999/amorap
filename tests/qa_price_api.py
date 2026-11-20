"""Admin price -> public catalog -> quote integration with isolated test DB."""
import tempfile, threading
from datetime import timedelta
from pathlib import Path
from qa_admin import TestDB, Client, server

with tempfile.TemporaryDirectory() as tmp:
    db=TestDB(str(Path(tmp)/'price.sqlite'));db.setup();server.db=db.connect
    class Quiet(server.Handler):
        def log_message(self,*args):pass
    host=server.ThreadingHTTPServer(('127.0.0.1',0),Quiet)
    th=threading.Thread(target=host.serve_forever,daemon=True);th.start()
    try:
        admin=Client(host.server_port);admin.login()
        initial=admin.get();rooms=initial['rooms'];rooms[0]['price']=817500;rooms[0]['reviewed']=True;rooms[0]['inventory']=2;rooms[0]['capacity']=2
        saved=admin.save('rooms',{'items':rooms},initial['revisions']['rooms'])
        assert saved['value'][0]['price']==817500
        # Different request/client verifies the saved rate persists, not just editor state.
        fresh=admin.get();assert fresh['rooms'][0]['price']==817500
        visitor=Client(host.server_port);catalog=visitor.send('GET','/api/catalog')
        assert catalog['rooms'][0]['price']==817500 and catalog['rooms'][0]['bookable'] is True
        start=server.today()+timedelta(days=9)
        cart={'checkin':start.isoformat(),'checkout':(start+timedelta(days=2)).isoformat(),'rooms':[{'id':rooms[0]['id'],'qty':1,'guests':2}],'addons':[],'services':[]}
        invoice=visitor.send('POST','/api/quote',cart)
        assert invoice['rooms'][0]['unit']==817500 and invoice['rooms'][0]['total']==1635000 and invoice['total']==1635000
        print('PASS backend: admin price saves -> public catalog shows same price -> quote uses same price over two nights')
    finally:
        host.shutdown();host.server_close();th.join()
