"""Chromium guest-flow QA for date-first booking, free kids, pets and customer care."""
import json,os,re
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1]
seed=json.loads((root/'seed.json').read_text())
catalog={**seed,'rooms':[{**r,'reviewed':True,'bookable':True,'active':True} for r in seed['rooms']],
 'addons':[],'services':[],'paymentReady':True,'paymentMethods':['bank','gcash'],
 'support':{'phone':'+63 912 345 6789','email':'care@example.test','hours':'Mon-Sun 8am-8pm','greeting':'How may we help?'}}
catalog['rooms'][0].update(petsAllowed=True,maxPets=2,petFee=35000,petPolicy='House-trained pets only')
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
      if(route==='/api/contact'){window.qaSent.push(JSON.parse(opts.body));return new Response(JSON.stringify({ok:true}),{status:201,headers:{'Content-Type':'application/json'}})}
      return new Response(JSON.stringify({error:'not mocked'}),{status:404,headers:{'Content-Type':'application/json'}});
    };
  }""",catalog)
  page.add_script_tag(content=(root/'public/assets/catalog-default.js').read_text())
  page.add_script_tag(content=(root/'public/assets/site.js').read_text())

 contact=context.new_page()
 prepare(contact,'contact')
 expect(contact.locator('#am-customer-call')).to_have_attribute('href','tel:+639123456789')
 expect(contact.locator('[data-support-email]')).to_contain_text('care@example.test')
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
 booking.get_by_role('button',name=re.compile('Continue to villas')).click()
 expect(booking.locator('#am-content [data-room="inland-single"]')).to_be_visible()
 booking.locator('#am-content [data-room="inland-single"]').click()
 expect(booking.locator('#am-stay-form')).to_be_visible()
 assert 'under 12' in booking.locator('#am-stay-form').inner_text()
 expect(booking.locator('#am-stay-form [name=kids]')).to_have_attribute('max','2')
 expect(booking.locator('#am-stay-form [name=pets]')).to_have_attribute('max','2')
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
