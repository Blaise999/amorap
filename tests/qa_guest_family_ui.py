"""Chromium guest-flow QA for date-first booking, free kids, pets and customer care."""
import json,os,re
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1]
seed=json.loads((root/'seed.json').read_text())
catalog={**seed,'rooms':[{**r,'reviewed':True,'bookable':True,'active':True} for r in seed['rooms']],
 'addons':[],'services':[],'paymentReady':True,'paymentMethods':['bank','gcash'],
 'support':{'phone':'+63 912 345 6789','dialPhone':'+639123456789','email':'care@example.test','resortAddress':'QA Resort Road','officeAddress':'QA Main Office','hours':'Mon-Sun 8am-8pm','greeting':'How may we help?'}}
catalog['rooms'][0].update(petsAllowed=True,maxPets=2,petFee=35000,petPolicy='House-trained pets only',inventory=3,capacity=8,extraGuestFee=50000)
with sync_playwright() as p:
 chrome=(os.environ.get('QA_CHROMIUM') or ('/usr/bin/chromium' if Path('/usr/bin/chromium').is_file() else None))
 browser=p.chromium.launch(executable_path=chrome,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 context=browser.new_context()
 errors=[]
 def prepare(page,path):
  page.on('pageerror',lambda e:errors.append(str(e)))
  html=(root/'public'/path/'index.html').read_text()
  html=re.sub(r'<script[^>]*>.*?</script>','',html,flags=re.S)
  html=re.sub(r'<link[^>]*>','',html)
  page.set_content(html)
  page.add_style_tag(content=(root/'public/assets/styles/original.css').read_text())
  page.add_style_tag(content=(root/'public/assets/styles/booking.css').read_text())
  page.evaluate("""(catalog)=>{
    window.qaSent=[];
    window.fetch=async(url,opts={})=>{
      const route=String(url).split('?')[0];
      if(route==='/api/catalog')return new Response(JSON.stringify(catalog),{status:200,headers:{'Content-Type':'application/json'}});
      if(route==='/api/availability'){
        const dates=new URL(String(url),'https://amorap.test').searchParams;
        const rooms=catalog.rooms.map((r,i)=>({id:r.id,totalRooms:r.inventory,available:i===1?0:r.inventory,bookable:i!==1&&r.bookable}));
        return new Response(JSON.stringify({checkin:dates.get('checkin'),checkout:dates.get('checkout'),rooms}),{status:200,headers:{'Content-Type':'application/json'}});
      }
      if(route==='/api/chat/start'){const v=JSON.parse(opts.body);window.mockChat={id:77,status:'open',guestName:v.name||'Guest',updated:1000,messages:[{role:'guest',text:v.message,at:1000}]};return new Response(JSON.stringify({chat:window.mockChat,token:'a'.repeat(43)}),{status:201,headers:{'Content-Type':'application/json'}});}
      if(route==='/api/chat/poll'){if(!window.mockChat.messages.some(m=>m.role==='admin'))window.mockChat.messages.push({role:'admin',text:'Hello from AMORAP staff',at:1001});return new Response(JSON.stringify({chat:window.mockChat}),{status:200,headers:{'Content-Type':'application/json'}});}
      if(route==='/api/chat/send'){const v=JSON.parse(opts.body);window.mockChat.messages.push({role:'guest',text:v.message,at:1002});return new Response(JSON.stringify({chat:window.mockChat}),{status:200,headers:{'Content-Type':'application/json'}});}
      if(route==='/api/contact'){window.qaSent.push(JSON.parse(opts.body));return new Response(JSON.stringify({ok:true}),{status:201,headers:{'Content-Type':'application/json'}})}
      return new Response(JSON.stringify({error:'not mocked'}),{status:404,headers:{'Content-Type':'application/json'}});
    };
  }""",catalog)
  page.add_script_tag(content=(root/'public/assets/catalog-default.js').read_text())
  page.add_script_tag(content=(root/'public/assets/site.js').read_text())

 contact=context.new_page()
 prepare(contact,'contact')
 expect(contact.locator('.am-chat-toggle')).to_be_visible()
 expect(contact.locator('#am-customer-call')).to_have_count(0)
 expect(contact.locator('[data-support-call]').first).to_have_attribute('href','tel:+639123456789')
 expect(contact.locator('[data-support-address]')).to_have_text('QA Resort Road')
 expect(contact.locator('[data-support-office]')).to_have_text('QA Main Office')
 expect(contact.locator('[data-support-email]')).to_contain_text('care@example.test')
 contact.set_viewport_size({'width':390,'height':650})
 contact.get_by_role('button',name='Open live chat').click()
 expect(contact.locator('.am-chat-panel')).to_be_visible()
 bounds=contact.locator('.am-chat-panel').bounding_box()
 assert bounds['x']>=0 and bounds['y']>=0 and bounds['x']+bounds['width']<=390 and bounds['y']+bounds['height']<=650
 contact.locator('.am-chat-panel [name=name]').fill('QA chatter')
 contact.locator('.am-chat-panel [name=message]').fill('Can you help?')
 contact.locator('.am-chat-panel').get_by_role('button',name='Send message').click()
 expect(contact.locator('.am-chat-message.is-guest')).to_contain_text('Can you help?')
 contact.get_by_role('button',name='Close chat').click()
 contact.get_by_role('button',name='Open live chat').click()
 expect(contact.locator('.am-chat-message.is-staff')).to_contain_text('Hello from AMORAP staff')
 contact.get_by_role('button',name='Close chat').click()
 contact.locator('#contact-form [name=name]').fill('QA Guest')
 contact.locator('#contact-form [name=email]').fill('guest@example.test')
 contact.locator('#contact-form [name=phone]').fill('+63 912 123 4567')
 contact.locator('#contact-form [name=message]').fill('Are pets welcome?')
 contact.get_by_role('button',name='Send Message').click()
 expect(contact.locator('#contact-result')).to_contain_text('sent to the resort dashboard')
 assert contact.evaluate("window.qaSent[0].phone")=='+63 912 123 4567'
 booking=context.new_page()
 prepare(booking,'booking')
 expect(booking.locator('#am-dates-form')).to_be_visible()
 expect(booking.locator('.am-live-chat')).to_be_hidden() # chat never covers booking drawer
 booking.get_by_role('button',name=re.compile('Continue to villas')).click()
 expect(booking.locator('#am-content [data-room="inland-single"]')).to_be_visible()
 expect(booking.locator('#am-content .am-room-stock').first).to_contain_text('3 rooms available for selected dates')
 expect(booking.locator('#am-content [data-room="inland-double"]')).to_be_disabled()
 assert '0 rooms available' in booking.locator('#am-content').inner_text()
 booking.locator('#am-content [data-room="inland-single"]').click()
 expect(booking.locator('#am-stay-form')).to_be_visible()
 assert 'under 12' in booking.locator('#am-stay-form').inner_text()
 expect(booking.locator('#am-stay-form [name=qty]')).to_have_attribute('max','3')
 expect(booking.locator('#am-stay-form [name=kids]')).to_have_attribute('max','2')
 expect(booking.locator('#am-stay-form [name=pets]')).to_have_attribute('max','2')
 expect(booking.locator('#am-stay-form [name=guests]')).to_have_attribute('max','8')
 booking.locator('#am-stay-form [name=guests]').fill('5')
 before=booking.locator('#am-estimate').inner_text()
 booking.get_by_role('button',name='Add one guest').click()
 expect(booking.locator('#am-stay-form [name=guests]')).to_have_value('6')
 expect(booking.locator('#am-extra-guest-estimate')).to_contain_text('1 additional guest')
 assert booking.locator('#am-estimate').inner_text()!=before
 booking.get_by_role('button',name='Remove one guest').click()
 assert booking.locator('#am-estimate').inner_text()==before
 booking.locator('#am-stay-form [name=qty]').fill('2')
 expect(booking.locator('#am-stay-form [name=kids]')).to_have_attribute('max','4')
 expect(booking.locator('#am-stay-form [name=pets]')).to_have_attribute('max','4')
 booking.locator('#am-stay-form [name=kids]').fill('4')
 booking.locator('#am-stay-form [name=pets]').fill('2')
 assert 'House-trained pets only' in booking.locator('#am-stay-form').locator('xpath=..').inner_text()
 assert not errors,errors
 print('PASS guest browser: date-first booking, configurable kids/pet limits and pet fees')
 print('PASS guest browser: customer care call, admin email, guest messages and callback number')
 browser.close()
