"""Local Chromium-only UI check with mocked admin API. No credentials or production writes."""
import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1]
seed=json.loads((root/'seed.json').read_text())
settings={**seed,'bookings':[],'messages':[],'revisions':{k:'r0' for k in ['rooms','addons','services','payment','support']},'sectionErrors':{},'release':'20261122-familycare1'}
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=(os.environ.get('QA_CHROMIUM') or ('/usr/bin/chromium' if Path('/usr/bin/chromium').is_file() else None)),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 page=browser.new_page(viewport={'width':1300,'height':920});page.set_default_timeout(4500)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 html=(root/'public/admin/index.html').read_text();import re
 html=re.sub(r'<script[^>]*>.*?</script>','',html,flags=re.S);html=re.sub(r'<link[^>]*>','',html)
 page.set_content(html)
 page.add_style_tag(content=(root/'public/assets/styles/booking.css').read_text())
 page.evaluate('''(settings)=>{window.qa=JSON.parse(JSON.stringify(settings));window.requests=[];window.fetch=async(path,opts={})=>{let name=String(path).split('/').pop();let status=200,body={};if(name==='session'||name==='login')body={csrf:'mock',version:'20261122-familycare1'};else if(name==='data')body=window.qa;else if(['rooms','addons','services','payment','support'].includes(name) && opts.method==='PUT'){let v=JSON.parse(opts.body);let next=name==='payment'?{...window.qa.payment,...v}:name==='support'?v:v.items;window.qa[name]=next;window.qa.revisions[name]='r'+window.requests.length;window.requests.push({name,value:next});body={value:next,revision:window.qa.revisions[name]};}else if(name==='upload')body={url:'/api/photo/0123456789abcdef0123456789abcdef.webp'};else if(name==='logout')body={};return new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}})}}''',settings)
 page.add_script_tag(content=(root/'public/assets/admin.js').read_text())
 expect(page.locator('#dashboard')).to_be_visible()
 expect(page.get_by_role('button',name='Rooms & prices')).to_be_visible()
 expect(page.locator('.am-simple-room')).to_have_count(len(settings['rooms']))
 first=page.locator('.am-simple-room').first
 expect(first.locator('summary.am-room-heading')).to_contain_text('₱')
 first.locator('summary.am-room-heading').click()
 expect(first.get_by_text('Nightly price (₱)')).to_be_visible()
 first.locator('[name=price]').fill('7777')
 first.locator('[name=maxKids]').fill('3')
 first.locator('[name=petsAllowed]').check()
 first.locator('[name=maxPets]').fill('1')
 first.locator('[name=petFee]').fill('250')
 first.get_by_role('button',name='Save room').click()
 expect(page.locator('#admin-message')).to_contain_text('Saved')
 saved=page.evaluate('window.qa.rooms[0].price');assert saved==777700,saved
 assert page.evaluate('window.qa.rooms[0].maxKids')==3
 assert page.evaluate('window.qa.rooms[0].petFee')==25000
 page.get_by_role('button',name='+ Add room').click()
 last=page.locator('.am-simple-room').last
 last.locator('[name=name]').fill('QA New Family Room')
 last.locator('[name=price]').fill('8999')
 last.locator('[name=inventory]').fill('2')
 last.locator('[name=capacity]').fill('4')
 last.locator('[name=reviewed]').check()
 last.get_by_role('button',name='Save room').click()
 expect(page.locator('#admin-message')).to_contain_text('Saved')
 saved_room=page.evaluate('window.qa.rooms.at(-1)')
 assert saved_room['name']=='QA New Family Room' and saved_room['price']==899900 and saved_room['inventory']==2,saved_room
 page.get_by_role('button',name='Customer care').click()
 expect(page.get_by_role('heading',name='Contact details')).to_be_visible()
 page.locator('[name=phone]').fill('+63 912 345 6789')
 page.locator('[name=hours]').fill('Everyday 8am-8pm')
 page.get_by_role('button',name='Save customer care').click()
 expect(page.locator('#admin-message')).to_contain_text('Customer care updated')
 assert page.evaluate('window.qa.support.phone')=='+63 912 345 6789'
 page.get_by_role('button',name='Payment options').click()
 expect(page.get_by_text('Local bank transfer',exact=True)).to_be_visible()
 expect(page.get_by_text('GCash',exact=True)).to_be_visible()
 page.locator('[name=bank]').fill('QA Bank')
 page.locator('[name=name]').fill('QA Owner')
 page.locator('[name=number]').fill('12345678')
 page.locator('[name=gcashName]').fill('QA GCash')
 page.locator('[name=gcashNumber]').fill('09123456789')
 page.get_by_role('button',name='Save bank details').click()
 page.get_by_role('button',name='Save GCash details').click()
 expect(page.locator('#admin-message')).to_contain_text('GCash details saved')
 saved=page.evaluate('window.qa.payment');assert saved['gcashNumber']=='09123456789' and saved['bank']=='QA Bank',saved
 page.locator('#admin-more-nav summary').click()
 page.locator('[data-tab=services]').click()
 expect(page.get_by_role('button',name='Add service')).to_be_visible()
 assert not errors,errors
 page.get_by_role('button',name='Rooms & prices').click()
 page.screenshot(path='/tmp/amorap_admin_easy_preview.png',full_page=True)
 print('PASS Chromium simple admin: edit room rate, add new room/price, save bank + GCash, More sections navigation, no JS errors')
 browser.close()
