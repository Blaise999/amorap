"""Isolated HTTP integration QA; never uses a real database or credentials.
Run `python tests/qa_admin.py`. SQLite is a TEST ADAPTER ONLY.
For optional Chromium UI coverage: `python tests/qa_admin.py --browser`.
"""
import base64, contextlib, copy, datetime, http.client, importlib.util, json, os, re, sqlite3, sys, tempfile, threading, time, types
from pathlib import Path
from http.cookies import SimpleCookie
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
if not importlib.util.find_spec('psycopg'):
    fake=types.ModuleType('psycopg'); fake.OperationalError=type('OperationalError',(Exception,),{}); fake.Error=Exception
    sys.modules['psycopg']=fake; rows=types.ModuleType('psycopg.rows'); rows.dict_row=None; sys.modules['psycopg.rows']=rows
import server
server.PREVIEW=False; server.USER='qa-admin'; server.PASSWORD='QA-only-test-password-123'; server.SECURE=False
class TestDB:
    def __init__(self,path):self.path=path;self.lock=threading.RLock();self.down=False
    @contextlib.contextmanager
    def connect(self,lock=True):
        if self.down:raise server.psycopg.OperationalError('simulated outage')
        with self.lock:
            c=sqlite3.connect(self.path);c.row_factory=lambda cur,row:dict(zip([x[0] for x in cur.description],row))
            class Adapter:
                def execute(self,q,args=()):
                    if 'pg_advisory' in q: return c.execute('SELECT 1')
                    return c.execute(q.replace('amorap_booking.','').replace('%s','?'),args)
                def commit(self):c.commit()
            try:
                yield Adapter();c.commit()
            except BaseException:c.rollback();raise
            finally:c.close()
    def setup(self):
        with self.connect() as c:
            for q in ['CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)','CREATE TABLE admin_sessions(token TEXT PRIMARY KEY,csrf TEXT,expiry INT)','CREATE TABLE photos(name TEXT PRIMARY KEY,mime TEXT,content BLOB)','CREATE TABLE reservations(id TEXT PRIMARY KEY,token TEXT,status TEXT,created INT,expires INT,payload TEXT,reference TEXT)','CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT,created INT,payload TEXT)']:c.execute(q)
            for k,v in server.SEED.items():c.execute('INSERT INTO settings VALUES(?,?)',(k,json.dumps(v)))
class Client:
    def __init__(self,port):self.port=port;self.cookie='';self.csrf=''
    def send(self,method,path,data=None,expected=200,revision=None,csrf=True):
        hdr={};body=None
        if self.cookie:hdr['Cookie']=self.cookie
        if csrf and self.csrf:hdr['X-CSRF-Token']=self.csrf
        if revision:hdr['If-Match']=revision
        if data is not None:body=json.dumps(data);hdr['Content-Type']='application/json'
        con=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10);con.request(method,path,body,hdr);r=con.getresponse();raw=r.read();cookie=r.getheader('Set-Cookie');status=r.status;con.close()
        if cookie:
            ck=SimpleCookie(cookie);self.cookie=f'{server.SESSION_COOKIE}='+ck[server.SESSION_COOKIE].value
        assert status==expected,(method,path,status,expected,raw[:300]);return json.loads(raw) if path.startswith('/api/') and not path.startswith('/api/photo/') else raw
    def login(self):self.csrf=self.send('POST','/api/admin/login',{'username':server.USER,'password':server.PASSWORD})['csrf']
    def get(self,p='data',expected=200):return self.send('GET','/api/admin/'+p,expected=expected)
    def save(self,key,body,rev=None,expected=200):return self.send('PUT','/api/admin/'+key,body,expected,rev)

def http_tests(port,db):
    a=Client(port); b=Client(port); guest=Client(port)
    a.get('data',401);a.send('POST','/api/admin/login',{'username':server.USER,'password':'wrong'},401);a.login();assert a.get('session')['csrf']==a.csrf
    d=a.get();assert a.get()==d
    assert 'amora' in a.cookie
    db.down=True;a.get('data',503);a.get('session',503);db.down=False;assert a.get('session')['csrf']==a.csrf
    print('PASS authentication, session refresh, temporary outage recovery, unauthenticated rejection')
    b.login();before=b.get();rows=d['rooms'];r=rows[0];r.update(name='QA Villa',category='QA Category',description='Updated QA description',price=520000,capacity=3,inventory=3,bed='King bed',size='42 sqm',policy='QA policy',amenities=['Wi-Fi','Pool'],reviewed=True,active=True)
    a.send('PUT','/api/admin/rooms',{'items':rows},403,csrf=False)
    img=(ROOT/'public/assets/villas/inland-resort.webp').read_bytes();up=a.send('POST','/api/admin/upload',{'data':base64.b64encode(img).decode()})['url'];r['images']=[up,r['images'][0]];assert guest.send('GET',up)==img
    a.send('POST','/api/admin/upload',{'data':'bm90IGFuIGltYWdl'},400)
    new=copy.deepcopy(r);new.update(id='qa-villa',name='QA New Villa',active=False);rows.append(new)
    saved=a.save('rooms',{'items':rows},d['revisions']['rooms']);assert saved['value'][0]==r
    b.save('rooms',{'items':before['rooms']},before['revisions']['rooms'],409)
    cat=guest.send('GET','/api/catalog');assert cat['rooms'][0]['name']==r['name'] and cat['rooms'][0]['bookable'] and all(x['id']!='qa-villa' for x in cat['rooms'])
    rows.pop();r['images'].reverse();r['images'].pop();a.save('rooms',{'items':rows},saved['revision']);assert a.get()['rooms'][0]['images']==r['images'];assert not any(x['id']=='qa-villa' for x in a.get()['rooms'])
    print('PASS villa add/edit/delete, photo upload/serve/reorder/remove, visibility, reviewed rates, stale-write rejection, CSRF protection')
    d=a.get(); extras=d['addons'];extras[0].update(active=True,price=55000,name='QA breakfast',description='QA meal',basis='night');extras.append({'id':'qa-extra','name':'QA extra','description':'','basis':'stay','active':False,'price':5000});s=a.save('addons',{'items':extras},d['revisions']['addons']);extras.pop();a.save('addons',{'items':extras},s['revision']);assert guest.send('GET','/api/catalog')['addons'][0]['name']=='QA breakfast'
    services=d['services'];services[0].update(name='QA event',description='Updated service',price=3000000,capacity=60,reviewed=True);services[1].update(name='QA dining',price=50000,capacity=25,reviewed=True);services.append({'id':'qa-service','kind':'dining','name':'QA new service','description':'','price':5000,'capacity':5,'active':True,'reviewed':True});s=a.save('services',{'items':services},d['revisions']['services']);services.pop();a.save('services',{'items':services},s['revision']);assert guest.send('GET','/api/catalog')['services'][0]['name']=='QA event'
    a.save('payment',{'bank':'Partial'},d['revisions']['payment'],400);pay={'bank':'QA bank (not real)','name':'Test only','number':'00000','instructions':'No actual transfers.'};s=a.save('payment',pay,d['revisions']['payment']);assert all(a.get()['payment'][k]==v for k,v in pay.items())
    print('PASS extras and services add/edit/remove, bank settings validation and persistence')
    tomorrow=server.today()+datetime.timedelta(days=2);nextday=tomorrow+datetime.timedelta(days=1)
    guest_data={'name':'QA Guest','email':'qa@example.test','phone':'000','requests':'Test'}
    cart={'checkin':tomorrow.isoformat(),'checkout':nextday.isoformat(),'rooms':[{'id':r['id'],'qty':1,'guests':2}],'addons':[{'id':extras[0]['id'],'qty':1}],'services':[{'id':services[0]['id'],'date':tomorrow.isoformat(),'time':'12:00','guests':10,'occasion':'QA Event'},{'id':services[1]['id'],'date':tomorrow.isoformat(),'time':'13:00','guests':2,'occasion':''}]}
    q=guest.send('POST','/api/quote',cart);assert q['total']==3675000,(q['total'],q)
    booking=guest.send('POST','/api/bookings',{**cart,'expectedTotal':q['total'],'guest':guest_data},201);bid=booking['booking']['id'];tok=booking['token'];assert booking['booking']['payment']['method']=='bank' and all(booking['booking']['payment'][k]==v for k,v in pay.items())
    guest.send('POST','/api/payment-reference',{'id':bid,'token':tok,'reference':'QA transfer'});assert a.get()['bookings'][0]['reference']=='QA transfer'
    v=a.send('POST','/api/admin/status',{'id':bid,'status':'confirmed'});assert v['booking']['status']=='confirmed';guest.send('POST','/api/quote',cart,409)
    v=a.send('POST','/api/admin/status',{'id':bid,'status':'cancelled'});assert v['booking']['status']=='cancelled';guest.send('POST','/api/quote',cart)
    a.send('POST','/api/admin/status',{'id':bid,'status':'confirmed'},400)
    guest.send('POST','/api/contact',{'name':'QA sender','email':'qa@example.test','message':'QA contact'},201);assert a.get()['messages'][0]['message']=='QA contact'
    a.save('payment',dict.fromkeys(pay,''),s['revision']);assert not guest.send('GET','/api/catalog')['paymentReady'];assert a.get()['bookings'][0]['payment']['method']=='bank'
    guest.send('POST','/api/bookings',{**cart,'guest':guest_data},409)
    print('PASS mixed checkout, bank snapshot, transfer review, confirm/cancel, conflict, contact inbox, payment disable')
    token=a.cookie;a.send('POST','/api/admin/logout',{});a.cookie=token;a.get('session',401);assert b.get('session')['csrf']==b.csrf
    with db.connect() as c:c.execute('UPDATE admin_sessions SET expiry=0')
    b.get('session',401);b.login();b.get()
    for path in ['/','/admin/','/villas/','/events/','/restaurant/','/about/','/careers/','/booking/','/checkout/','/contact/']:assert guest.send('GET',path)
    guest.send('GET','/server.py',expected=404)
    print('PASS explicit logout, expired sessions, other admin session unaffected, 10 pages and private source denied')

def browser_tests(port,db):
    from playwright.sync_api import sync_playwright, expect
    # Offline DOM/JavaScript coverage using real HTTP handler via an explicit fetch bridge.
    # This verifies browser interactions, not real browser cookie transport or hosted rendering.
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ.get('QA_CHROMIUM','/usr/bin/chromium'),args=['--no-sandbox','--disable-dev-shm-usage'],headless=True)
        context=browser.new_context();errors=[];faults={'data':0,'session':0,'rooms':0};cookie={'value':'','drop_next_login':False};extra_faults={}
        def bridge(path,options):
            part=path.split('?')[0].rsplit('/',1)[-1]
            if extra_faults.get(part):
                status,payload=extra_faults[part].pop(0);return {'status':status,'body':json.dumps(payload)}
            if path.startswith('/api/admin/') and faults.get(part,0)>0:
                faults[part]-=1;return {'status':503,'body':json.dumps({'error':'Simulated temporary outage'})}
            headers=options.get('headers',{});headers['Host']='127.0.0.1:'+str(port)
            if cookie['value']:headers['Cookie']=cookie['value']
            conn=http.client.HTTPConnection('127.0.0.1',port,timeout=15);conn.request(options.get('method') or 'GET',path,body=options['body'].encode('utf-8') if options.get('body') is not None else None,headers=headers);res=conn.getresponse();raw=res.read();status=res.status;ck=res.getheader('Set-Cookie');conn.close()
            if ck:
                if part=='login' and cookie['drop_next_login']:cookie['drop_next_login']=False;cookie['value']=''
                else:cookie['value']=server.SESSION_COOKIE+'='+SimpleCookie(ck)[server.SESSION_COOKIE].value
            return {'status':status,'body':raw.decode('utf-8')}
        def open_page(old=None):
            if old:old.close()
            p=context.new_page();p.on('pageerror',lambda x:errors.append(str(x)));p.on('dialog',lambda d:d.accept());p.expose_function('qaFetch',bridge)
            # All executable app JavaScript is loaded unchanged, local HTML/CSS only.
            html=(ROOT/'public/admin/index.html').read_text();html=re.sub(r'<script[^>]*>.*?</script>','',html,flags=re.S);html=re.sub(r'<link[^>]*>','',html)
            p.set_content(html);p.add_style_tag(content=(ROOT/'public/assets/styles/booking.css').read_text());p.evaluate("()=>{window.fetch=async(path,options={})=>{const r=await window.qaFetch(path,{method:options.method,headers:options.headers||{},body:options.body});return new Response(r.body,{status:r.status,headers:{'Content-Type':'application/json'}})};}");p.add_script_tag(content=(ROOT/'public/assets/admin.js').read_text());return p
        page=open_page();expect(page.locator('#admin-login')).to_be_visible()
        def login():
            page.locator('[name=username]').fill(server.USER);page.locator('[name=password]').fill(server.PASSWORD);page.locator('#login-form button').click();expect(page.locator('#dashboard')).to_be_visible()
        cookie['drop_next_login']=True;page.locator('[name=username]').fill(server.USER);page.locator('[name=password]').fill(server.PASSWORD);page.locator('#login-form button').click();expect(page.locator('#login-error')).to_contain_text('session cookie was not returned');expect(page.locator('#dashboard')).to_be_hidden()
        faults['data']=1;login();expect(page.get_by_text('Retry loading dashboard')).to_be_visible();expect(page.locator('#admin-login')).to_be_hidden();page.get_by_text('Retry loading dashboard').click();expect(page.get_by_text('Save all villas',exact=True)).to_be_visible()
        page=open_page(page);expect(page.get_by_text('Save all villas',exact=True)).to_be_visible();faults['session']=1;page=open_page(page);expect(page.locator('#retry-session')).to_be_visible();expect(page.locator('#admin-login')).to_be_hidden();page.locator('#retry-session').click();expect(page.get_by_text('Save all villas',exact=True)).to_be_visible()
        extra_faults['data']=[(401,{'error':'Proxy authorization response'})];page.get_by_text('Refresh',exact=True).click();expect(page.locator('#admin-error')).to_contain_text('Proxy authorization response');expect(page.locator('#dashboard')).to_be_visible();extra_faults['data']=[(401,{'error':'Temporary missing cookie','code':'SESSION_MISSING'})];page.get_by_text('Refresh',exact=True).click();expect(page.locator('#admin-message')).to_contain_text('Dashboard refreshed');expect(page.locator('#dashboard')).to_be_visible()
        # A broken section must not hide healthy sections or offer unsafe saves.
        with db.connect() as c:
            saved_services=c.execute('SELECT value FROM settings WHERE key=%s',('services',)).fetchone()['value'];c.execute('UPDATE settings SET value=%s WHERE key=%s',('not-json','services'))
        page.locator('[data-tab=services]').click();expect(page.get_by_text('Section temporarily unavailable')).to_be_visible();expect(page.get_by_text('Save all services')).to_have_count(0);expect(page.locator('#admin-login')).to_be_hidden()
        page.locator('[data-tab=rooms]').click();expect(page.get_by_text('Save all villas')).to_be_visible()
        with db.connect() as c:c.execute('UPDATE settings SET value=%s WHERE key=%s',(saved_services,'services'))
        page.locator('[data-tab=services]').click();expect(page.get_by_text('Save all services')).to_be_visible();page.locator('[data-tab=rooms]').click();expect(page.get_by_text('Save all villas')).to_be_visible()
        card=page.locator('[data-index="0"]');card.locator('summary').click();card.locator('[name=name]').fill('QA Browser Villa');faults['rooms']=1;page.get_by_text('Save all villas',exact=True).click();expect(page.locator('#admin-error')).to_contain_text('Simulated');expect(card.locator('[name=name]')).to_have_value('QA Browser Villa');page.get_by_text('Save all villas',exact=True).click();expect(page.locator('#admin-message')).to_contain_text('Saved successfully');expect(card.locator('summary')).to_contain_text('QA Browser Villa')
        # Force session expiration during a pending edit, then recover the DOM draft.
        card.locator('summary').click();card.locator('[name=description]').fill('Preserve unsaved browser draft');with_expire(db)
        page.get_by_text('Save all villas',exact=True).click();expect(page.locator('#admin-login')).to_be_visible();expect(page.locator('#login-error')).to_contain_text('unsaved');login();expect(card.locator('[name=description]')).to_have_value('Preserve unsaved browser draft');page.get_by_text('Save all villas',exact=True).click();expect(page.locator('#admin-message')).to_contain_text('Saved successfully')
        # Exercise the actual dashboard buttons for every editable tab, including upload and catalog deletion.
        def saved():expect(page.locator('#admin-message')).to_contain_text('Saved successfully')
        def select_tab(tab,heading):
            page.locator('[data-tab='+tab+']').click();expect(page.locator('#admin-content h2')).to_have_text(heading)
        page.get_by_text('Add villa',exact=True).click();last=page.locator('[data-index]').last;last.locator('[name=name]').fill('UI villa');last.locator('[name=category]').fill('UI category');last.locator('[name=price]').fill('1234.56');last.locator('[name=capacity]').fill('2');last.locator('[name=inventory]').fill('1');last.locator('[name=reviewed]').check();last.locator('[data-upload]').set_input_files([str(ROOT/'public/assets/villas/inland-resort.webp'),str(ROOT/'public/assets/villas/ocean-resort.webp')]);expect(last.locator('[data-remove-photo]')).to_have_count(2);last.locator('[data-cover-photo]').click();last.locator('[data-remove-photo]').last.click();page.get_by_text('Save all villas',exact=True).click();saved()
        check=Client(port);cat=check.send('GET','/api/catalog');v=next(x for x in cat['rooms'] if x['name']=='UI villa');assert v['price']==123456 and len(v['images'])==1 and v['bookable']
        last.locator('summary').click();last.get_by_text('Remove villa from catalog').click();page.get_by_text('Save all villas',exact=True).click();saved();assert all(x['name']!='UI villa' for x in check.send('GET','/api/catalog')['rooms'])
        select_tab('addons','Optional extras');page.get_by_text('Add extra',exact=True).click();last=page.locator('[data-index]').last;last.locator('[name=name]').fill('UI extra');last.locator('[name=price]').fill('123');page.get_by_text('Save all extras').click();saved();assert any(x['name']=='UI extra' for x in check.send('GET','/api/catalog')['addons']);last.locator('summary').click();last.get_by_text('Remove extra').click();page.get_by_text('Save all extras').click();saved()
        select_tab('services','Events & dining');page.get_by_text('Add service',exact=True).click();last=page.locator('[data-index]').last;last.locator('[name=name]').fill('UI event');last.locator('[name=price]').fill('10000');last.locator('[name=capacity]').fill('30');last.locator('[name=reviewed]').check();last.locator('[data-upload]').set_input_files(str(ROOT/'public/assets/villas/inland-resort.webp'));expect(last.locator('[data-remove-photo]')).to_have_count(1);page.get_by_role('button',name='Save all services').click();saved();assert any(x['name']=='UI event' and x['bookable'] and len(x['images'])==1 for x in check.send('GET','/api/catalog')['services']);last.locator('summary').click();last.get_by_text('Remove service').click();page.get_by_role('button',name='Save all services').click();saved()
        select_tab('payment','Payment methods');page.locator('[name=bank]').fill('UI Test Bank');page.locator('[name=name]').fill('UI QA');page.locator('[name=number]').fill('000');page.locator('[name=instructions]').fill('Test only');page.locator('[name=gcashName]').fill('QA GCash');page.locator('[name=gcashNumber]').fill('09123456789');page.locator('[name=gcashInstructions]').fill('QA only');page.get_by_text('Save payment instructions').click();saved();assert check.send('GET','/api/catalog')['paymentMethods']==['bank','gcash']
        # New booking in the real API then confirm/cancel using browser controls.
        date=(server.today()+datetime.timedelta(days=4)).isoformat();cart={'rooms':[],'addons':[],'services':[{'id':'event-occasion','date':date,'time':'14:00','guests':5,'occasion':'UI QA'}],'guest':{'name':'UI Guest','email':'ui@example.test','phone':'000'},'paymentMethod':'bank'};v=check.send('POST','/api/bookings',cart,201);bid=v['booking']['id'];check.send('POST','/api/payment-reference',{'id':bid,'token':v['token'],'reference':'UI reference'})
        select_tab('bookings','Reservations');page.locator('#booking-filter').select_option('payment_review');record=page.locator('details').filter(has_text=bid);record.locator('summary').click();expect(record).to_contain_text('UI reference');record.get_by_text('Confirm verified payment').click();expect(page.locator('#admin-message')).to_contain_text('Reservation status updated');record.locator('summary').click();record.get_by_text('Cancel reservation').click();expect(record.locator('summary')).to_contain_text('cancelled')
        select_tab('messages','Contact messages');page.get_by_text('QA sender').click();expect(page.get_by_text('QA contact',exact=True)).to_be_visible()
        page.locator('#logout').click();expect(page.locator('#admin-login')).to_be_visible();page=open_page(page);expect(page.locator('#admin-login')).to_be_visible();assert not errors,errors
        # Public DOM consumes the saved catalog from the same API, without using the starter values.
        for rel,expected,selector in [('villas','QA Browser Villa','#villa-catalog'),('events','QA event','#event-catalog'),('restaurant','QA dining','[data-dining-card]')]:
            p=context.new_page();p.on('pageerror',lambda x:errors.append(str(x)));p.expose_function('qaFetch',bridge)
            html=(ROOT/'public'/rel/'index.html').read_text();html=re.sub(r'<script[^>]*>.*?</script>','',html,flags=re.S);html=re.sub(r'<link[^>]*>','',html);p.set_content(html);p.evaluate("()=>{window.fetch=async(path,options={})=>{const r=await window.qaFetch(path,{method:options.method,headers:options.headers||{},body:options.body});return new Response(r.body,{status:r.status,headers:{'Content-Type':'application/json'}})};}");p.add_script_tag(content=(ROOT/'public/assets/catalog-default.js').read_text());p.add_script_tag(content=(ROOT/'public/assets/site.js').read_text());expect(p.locator(selector).filter(has_text=expected).first).to_contain_text(expected);assert p.locator(selector).filter(has_text=expected).first.locator('button[data-room],button[data-service]').count()>0;p.close()
        assert not errors,errors
        print('PASS public Chromium DOM: live villa, event and dining names and booking actions')
        print('PASS Chromium offline DOM dashboard: login + data outage, reload, session outage, save outage and retry, expired-session draft recovery, add/edit/remove, photo controls, bank settings, confirm/cancel, messages, logout; no uncaught JS errors')
        browser.close()

def with_expire(db):
    with db.connect() as c:c.execute('UPDATE admin_sessions SET expiry=0')

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as tmp:
        db=TestDB(str(Path(tmp)/'qa.sqlite'));db.setup();server.db=db.connect
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        h=server.ThreadingHTTPServer(('127.0.0.1',0),Quiet);t=threading.Thread(target=h.serve_forever,daemon=True);t.start()
        try:http_tests(h.server_port,db);browser_tests(h.server_port,db) if '--browser' in sys.argv else None
        finally:h.shutdown();h.server_close()
