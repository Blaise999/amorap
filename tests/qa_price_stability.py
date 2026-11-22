"""Price continuity tests (real Chromium + mocked API; never contacts production)."""
import json, os, re, time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
root=Path(__file__).resolve().parents[1]
seed=json.loads((root/'seed.json').read_text())

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('QA_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page(viewport={'width':1100,'height':950});page.set_default_timeout(9000)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    # CUSTOMER: public catalog contains a rate different from fallback seed.
    catalog={**seed,'rooms':[dict(r,price=(760000 if i==0 else r['price']),reviewed=True,bookable=True) for i,r in enumerate(seed['rooms'])], 'paymentReady':True,'paymentMethods':['bank','gcash']}
    html=(root/'public/booking/index.html').read_text()
    html=re.sub(r'<script[^>]*>.*?</script>','',html,flags=re.S)
    html=re.sub(r'<link[^>]*>','',html)
    page.set_content(html)
    page.add_style_tag(content=(root/'public/assets/styles/booking.css').read_text())
    page.evaluate("""(catalog)=>{
     window.CATALOG=catalog;window.calls=[];window.fetch=async (url,opts={})=>{
       const endpoint=String(url).replace('/api/','');window.calls.push(endpoint);
       let body;
       if(endpoint==='catalog')body=window.CATALOG;
       else if(endpoint==='quote'){
         await new Promise(r=>setTimeout(r,300));
         let cart=JSON.parse(opts.body);let nights=(new Date(cart.checkout)-new Date(cart.checkin))/86400000;
         const rs=cart.rooms.map(x=>({id:x.id,name:window.CATALOG.rooms.find(r=>r.id===x.id).name,qty:x.qty,guests:x.guests,total:window.CATALOG.rooms.find(r=>r.id===x.id).price*x.qty*nights}));
         body={checkin:cart.checkin,checkout:cart.checkout,nights,rooms:rs,addons:[],services:[],total:rs.reduce((n,r)=>n+r.total,0),currency:'PHP'};
       } else body={};
       return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
     };
    }""",catalog)
    page.add_script_tag(content=(root/'public/assets/catalog-default.js').read_text())
    page.add_script_tag(content=(root/'public/assets/site.js').read_text())
    expect(page.locator('#am-modal-title')).to_have_text('Choose your dates')
    page.locator('#am-dates-form [name=checkin]').fill('2026-12-14')
    page.locator('#am-dates-form [name=checkout]').fill('2026-12-16')
    page.locator('#am-dates-form [type=submit]').click()
    expect(page.locator('#am-modal-title')).to_have_text('Choose your reservation')
    expect(page.locator('#am-content .am-room-card').first).to_contain_text('₱7,600.00')
    assert '₱4,500.00' not in page.locator('#am-content').inner_text(), 'Wrong default price flashed over live rate'
    page.locator('#am-content [data-room]').first.click()
    expect(page.locator('#am-stay-form')).to_be_visible()
    expect(page.locator('.am-price-persistent')).to_contain_text('₱7,600.00')
    expect(page.locator('#am-estimate')).to_contain_text('₱15,200.00')
    page.locator('#am-stay-form [type=submit]').click()
    # Immediately after advancing, an estimated total remains visible while quote loads.
    expect(page.locator('.am-price-persistent')).to_contain_text('₱15,200.00')
    expect(page.locator('[data-reservation-total]')).to_contain_text('₱15,200.00')
    page.locator('[data-checkout]').click()
    expect(page.locator('.am-price-persistent')).to_contain_text('₱15,200.00')
    expect(page.locator('#am-guest-form')).to_be_visible()
    expect(page.locator('.am-guest-form') if False else page.locator('#am-guest-form .am-total')).to_contain_text('₱15,200.00')
    # Direct 'Book this villa' from a visible villa listing: show the price on the dates step.
    page.locator('.am-close').click()
    page.locator('#villa-catalog [data-room]').first.click()
    expect(page.locator('#am-modal-title')).to_have_text('Choose your dates')
    expect(page.locator('.am-price-persistent')).to_contain_text('₱7,600.00')
    assert not errors,errors
    print('PASS guest: live price does not flash back to seed; price visible on dates, details, checkout loading and final checkout')
    # ADMIN: open room, edit price, save, confirm room editor stays open and server value persists.
    admin=browser.new_page(viewport={'width':1200,'height':900});admin.set_default_timeout(9000)
    admin_errors=[];admin.on('pageerror',lambda e:admin_errors.append(str(e)))
    html=(root/'public/admin/index.html').read_text();html=re.sub(r'<script[^>]*>.*?</script>','',html,flags=re.S);html=re.sub(r'<link[^>]*>','',html)
    admin.set_content(html);admin.add_style_tag(content=(root/'public/assets/styles/booking.css').read_text())
    admin.evaluate("""(s)=>{
      window.qa={...s,bookings:[],messages:[],sectionErrors:{},revisions:{rooms:'0',services:'0',addons:'0',payment:'0'},release:'20261122-receipt1'};
      window.fetch=async (url,opts={})=>{
        const name=String(url).split('/').pop();let data={};
        if(name==='session')data={csrf:'test',version:'20261122-receipt1'};
        else if(name==='data')data=window.qa;
        else if(name==='rooms'&&opts.method==='PUT'){
           window.qa.rooms=JSON.parse(opts.body).items;window.qa.revisions.rooms='1';data={value:window.qa.rooms,revision:'1'};
        }
        return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
      };
    }""",seed)
    admin.add_script_tag(content=(root/'public/assets/admin.js').read_text())
    expect(admin.locator('#dashboard')).to_be_visible()
    room=admin.locator('.am-simple-room').first
    room.locator('summary.am-room-heading').click()
    expect(room.locator('[name=price]')).to_be_visible()
    room.locator('[name=price]').fill('8175')
    expect(room.locator('[data-price-preview]')).to_have_text('₱8,175.00')
    room.get_by_role('button',name='Save room').click()
    expect(admin.locator('#admin-message')).to_contain_text('Saved successfully')
    room=admin.locator('.am-simple-room').first
    assert room.evaluate('(x)=>x.open'), 'Room editor unexpectedly closed after saving price'
    expect(room.locator('[name=price]')).to_have_value('8175')
    expect(room.locator('[data-price-preview]')).to_have_text('₱8,175.00')
    assert admin.evaluate('window.qa.rooms[0].price')==817500
    assert not admin_errors,admin_errors
    print('PASS admin: rate preview updates immediately, persists to API and editor stays open after save')
    browser.close()
