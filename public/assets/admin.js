'use strict';
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)],esc=v=>String(v??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x])),money=v=>new Intl.NumberFormat('en-PH',{style:'currency',currency:'PHP'}).format(v/100),phDate=v=>new Date(v*1000).toLocaleString('en-PH',{timeZone:'Asia/Manila'});
let csrf='',model=null,tab='rooms',dirty=false,busy=false;
let committed={rooms:[],services:[],addons:[]};
const snapshot=x=>JSON.parse(JSON.stringify(x));
const isSaved=(kind,id)=>committed[kind]?.some(item=>item.id===id)===true;
const area=$('#admin-content');
const AUTH_FAILURES=new Set(['SESSION_MISSING','SESSION_INVALID','SESSION_EXPIRED']);
const ADMIN_VERSION='20261122-receipt1';
class RequestError extends Error{constructor(message,status=0,code=''){super(message);this.status=status;this.code=code}}
const isSessionFailure=e=>e.status===401&&AUTH_FAILURES.has(e.code);
async function request(p,method='GET',body,rev='',controller=new AbortController(),timeout=60000){
 const timer=setTimeout(()=>controller.abort(),timeout);let r,data;
 try{r=await fetch('/api/admin/'+p,{method,credentials:'same-origin',cache:'no-store',headers:{...(body!==undefined?{'Content-Type':'application/json'}:{}),...(csrf?{'X-CSRF-Token':csrf}:{}),...(rev?{'If-Match':rev}:{})},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal});data=await r.json();}
 catch(e){if(r&&e.name!=='AbortError')throw new RequestError('The admin API returned an invalid response. Check the hosting service and retry.',r.status);throw new RequestError('Connection interrupted. Retry without closing this page; unsaved edits are retained.')}
 finally{clearTimeout(timer)}
 if(!r.ok)throw new RequestError((data?.error||'Request failed')+(p==='data'&&r.status===500&&!data?.reference?' Check the Vercel runtime logs for GET /api/admin/data.':''),r.status,data?.code||'');
 return data;
}
function validateSession(s){if(s?.version!==ADMIN_VERSION||typeof s.csrf!=='string')throw new RequestError('The hosting service is running a different admin backend version. Redeploy the Python server and public files together.');return s;}
async function readSession(){const s=validateSession(await request('session'));csrf=s.csrf;return s;}
function sessionEnded(e){loginMode((e.code==='SESSION_MISSING'?'Your browser stopped sending the admin session cookie. Use the same website address and allow first-party cookies.': 'Your admin session ended. Please sign in again.')+(dirty?' Your unsaved edits are still here.':''));}
async function api(p,method='GET',body,rev='',retry=true){
 try{return await request(p,method,body,rev)}catch(e){
  if(p==='login'||p==='session')throw e;
  if(retry&&((e.status===403&&e.code==='CSRF_INVALID')||isSessionFailure(e))){
   try{await readSession()}catch(check){if(isSessionFailure(check))sessionEnded(check);throw check;}
   // Only retry a request that the server explicitly rejected BEFORE mutation.
   return api(p,method,body,rev,false);
  }
  if(isSessionFailure(e)){
   try{await readSession()}catch(check){if(isSessionFailure(check))sessionEnded(check);throw check;}
   throw new RequestError('Your session is active, but this request was rejected. Retry the action.',e.status);
  }
  throw e;
 }
}
function loginMode(message=''){$('#auth-loading').hidden=true;$('#dashboard').hidden=true;$('#logout').hidden=true;$('#admin-login').hidden=false;$('#login-error').textContent=message;csrf='';}
function dashboard(){$('#auth-loading').hidden=true;$('#admin-login').hidden=true;$('#dashboard').hidden=false;$('#logout').hidden=false;}
function notice(msg='',err=''){$('#admin-message').textContent=msg;$('#admin-error').textContent=err;}
function authLoading(message,retry=false){$('#auth-loading').hidden=false;$('#auth-message').textContent=message;$('#retry-session').hidden=!retry;$('#admin-login').hidden=true;$('#dashboard').hidden=true;$('#logout').hidden=true;}
function setBusy(value){busy=value;area.inert=value;$$('[data-tab]').forEach(b=>b.disabled=value);$('#logout').disabled=value;$('#login-form button').disabled=value;$('#retry-session').disabled=value;$('#dashboard').setAttribute('aria-busy',String(value));}
async function run(fn){if(busy)return;heartbeatController?.abort();setBusy(true);try{await fn()}catch(x){if(!$('#dashboard').hidden)notice('',x.message);else if(!$('#admin-login').hidden&&x.status!==401)$('#login-error').textContent=x.message;}finally{setBusy(false)}}
const DASHBOARD_RELEASE='20261122-receipt1';
async function refresh(){const next=await api('data');if(!next||!next.revisions||!next.sectionErrors||next.release!==DASHBOARD_RELEASE)throw Error('Dashboard backend is outdated. Redeploy the API and website together.');for(const k of ['rooms','addons','services','bookings','messages'])if(!Array.isArray(next[k])&&!next.sectionErrors[k])throw Error('Dashboard data is incomplete. Retry loading.');if(!next.sectionErrors.payment&&(!next.payment||typeof next.payment!=='object'||Array.isArray(next.payment)))throw Error('Payment settings are incomplete.');for(const k of ['rooms','addons','services','payment'])if(!next.sectionErrors[k]&&typeof next.revisions[k]!=='string')throw Error('Missing revision for '+k+'.');model=next;dirty=false;for(const key of ['rooms','services','addons'])if(!next.sectionErrors?.[key])committed[key]=snapshot(next[key]);try{render()}catch(e){model.sectionErrors[tab]={error:'This section contains data the dashboard cannot display. Other sections remain available.',code:'DISPLAY_FORMAT_ERROR'};render()}}

async function loadDashboard(){dashboard();if(dirty&&model){notice('Signed in again. Your unsaved edits are still here.');return;}if(!model)area.innerHTML='<p class="am-note">Loading dashboard…</p>';try{await refresh();notice()}catch(x){if($('#dashboard').hidden)return;if(!model)area.innerHTML='<p class="am-note">Your session is active, but dashboard data could not be loaded.</p><button class="am-secondary" data-refresh>Retry loading dashboard</button>';notice('',x.message)}}
async function restoreSession(){authLoading('Checking your session…');try{await readSession();await loadDashboard()}catch(x){if(isSessionFailure(x)){if(dirty)sessionEnded(x);else loginMode(x.code==='SESSION_EXPIRED'?'Your session has expired. Please sign in again.':'');}else authLoading(x.message,true)}}
let heartbeatError='',heartbeatController=null;
async function heartbeat(){
 if(busy||heartbeatController||$('#dashboard').hidden||document.visibilityState==='hidden')return;
 const controller=new AbortController();heartbeatController=controller;const stillActive=()=>!controller.signal.aborted&&!busy&&!$('#dashboard').hidden;
 try{
  let s;try{s=await request('session','GET',undefined,'',controller,8000)}catch(e){if(!isSessionFailure(e)||!stillActive())throw e;s=await request('session','GET',undefined,'',controller,8000)}
  if(!stillActive())return;csrf=validateSession(s).csrf;if(heartbeatError&&$('#admin-error').textContent===heartbeatError)$('#admin-error').textContent='';heartbeatError='';
 }catch(e){if(!stillActive())return;if(isSessionFailure(e))sessionEnded(e);else{heartbeatError='Session check temporarily unavailable. Your dashboard remains open; retry when connected. '+e.message;$('#admin-error').textContent=heartbeatError;}}
 finally{if(heartbeatController===controller)heartbeatController=null;}
}
async function go(t){if(!model){await loadDashboard();return}if(t===tab)return;if(dirty&&!confirm('Discard unsaved changes?'))return;const old=tab;tab=t;try{await refresh();notice()}catch(x){tab=old;throw x}}
function applySaved(key,result,message='Saved successfully. Changes are now live.'){
 const expanded=tab===key?$$('[data-index][open]',area).map(el=>model[tab]?.[Number(el.dataset.index)]?.id).filter(Boolean):[];
 model[key]=result.value;model.revisions[key]=result.revision;
 if(committed[key])committed[key]=snapshot(result.value);
 dirty=false;render();
 if(tab===key&&expanded.length){
  $$('[data-index]',area).forEach(el=>{const r=model[tab][Number(el.dataset.index)];if(r&&expanded.includes(r.id))el.open=true;});
 }
 notice(message);
}
function field(name,label,val='',type='text',attrs=''){return `<label class="am-field">${esc(label)}<input name="${name}" type="${type}" value="${esc(val)}" ${attrs}></label>`}
function textarea(name,label,val='',full=true){return `<label class="am-field ${full?'am-full':''}">${esc(label)}<textarea name="${name}">${esc(val)}</textarea></label>`}
function toolbar(title,desc,addLabel='',saveLabel=''){return `<div class="am-admin-toolbar"><section><h2>${esc(title)}</h2><p class="am-note">${esc(desc)}</p></section><div>${addLabel?`<button class="am-secondary" data-add>${esc(addLabel)}</button>`:''}${saveLabel?`<button class="am-primary" data-save>${esc(saveLabel)}</button>`:''}<button class="am-secondary" data-refresh>Refresh</button></div></div>`}
function photos(r){return `<div class="am-admin-photos">${(r.images||[]).map((im,i)=>`<div class="am-admin-photo"><img src="${esc(im)}" loading="lazy" alt="${im.startsWith('/assets/villas/')?'Resort setting':'Uploaded photo'}">${im.startsWith('/assets/villas/')?'<small>Resort setting</small>':''}${i===0?'<small>Cover photo</small>':''}<button type="button" class="am-link" data-remove-photo="${i}" aria-label="Delete photo ${i+1}">Delete photo</button>${i>0?` · <button class="am-link" type="button" data-cover-photo="${i}">Make cover</button>`:''}</div>`).join('')}</div>`}
function deleteControl(kind,r){const label=kind==='rooms'?'villa':kind==='services'?'event / dining listing':'extra';return `<button class="am-danger am-delete-inline" type="button" data-delete aria-label="Delete ${esc(r.name||'new '+label)}">${isSaved(kind,r.id)?'Delete '+(kind==='rooms'?'villa':kind==='services'?'service':'extra'):'Discard draft'}</button>`}
function roomForm(r,i){const rate=r.price>0?money(r.price):'Add price',status=r.reviewed===true&&r.active&&r.price>0&&r.inventory>0&&r.capacity>0?'Bookable':r.active?'Needs details':'Hidden';return `<details class="am-admin-card am-simple-room" data-index="${i}" data-kind="rooms" ${r.name?'':'open'}><summary class="am-room-heading"><span class="am-room-thumb">${r.images?.[0]?`<img src="${esc(r.images[0])}" alt="" loading="lazy">`:'🏡'}</span><span class="am-room-heading-text"><strong>${esc(r.name||'New room')}</strong><small>${esc(r.category||'Villa')} · <b data-price-preview>${esc(rate)}</b> / night</small></span><span class="am-tag">${status}</span><span class="am-edit-hint">Edit</span></summary><div class="am-room-editor"><p class="am-simple-help">Edit the details below, then click <strong>Save room</strong>. Prices are in Philippine pesos (₱).</p><div class="am-room-primary-grid">${field('name','Room name',r.name,'text','required maxlength="120"')}${field('price','Nightly price (₱)',r.price===null?'':r.price/100,'number','min="0" step="0.01" max="1000000" placeholder="e.g. 4500"')}${field('inventory','Number of available rooms',r.inventory,'number','min="0" max="1000" step="1"')}${field('capacity','Guests per room',r.capacity,'number','min="0" max="100" step="1"')}</div><div class="am-simple-photo-block"><h3>Room pictures</h3><label class="am-upload-button">+ Add pictures <input type="file" data-upload accept="image/*" multiple></label><p class="am-simple-help">Pick photos from your phone or computer. Click Make cover for the main picture, then save the room.</p><div data-photos>${photos(r)}</div></div><details class="am-room-more"><summary>More room details (optional)</summary><div class="am-form-grid">${field('category','Room category',r.category)}${textarea('description','Description',r.description)}${field('bed','Bed setup',r.bed)}${field('size','Room size',r.size)}${textarea('amenities','Amenities — one per line',(r.amenities||[]).join('\n'))}${textarea('policy','Room policies',r.policy)}</div></details><div class="am-simple-publish"><label class="am-checkbox"><input name="active" type="checkbox" ${r.active?'checked':''}> Show this room on the website</label><label class="am-checkbox"><input name="reviewed" type="checkbox" ${r.reviewed===true?'checked':''}> Price and availability checked — allow bookings</label><small>Bookings also need a positive nightly price, room count, guest capacity and a configured payment method.</small></div><div class="am-room-action-bar"><button type="button" class="am-primary" data-save>Save room</button>${deleteControl('rooms',r)}</div></div></details>`}
function addonForm(r,i){return `<details class="am-admin-card" data-index="${i}" data-kind="addons" ${r.name?'':'open'}><summary class="am-summary"><span>${esc(r.name||'New extra')}</span>${deleteControl('addons',r)}</summary><div class="am-form-grid">${field('name','Extra name',r.name,'text','required')}${field('price','Price (PHP)',r.price===null?'':r.price/100,'number','min="0" step="0.01" max="1000000"')}${textarea('description','Description',r.description)}<label class="am-field">Charge<select name="basis"><option value="stay" ${r.basis==='stay'?'selected':''}>Per item / stay</option><option value="night" ${r.basis==='night'?'selected':''}>Per item / night</option></select></label><label class="am-checkbox"><input type="checkbox" name="active" ${r.active?'checked':''}> Available in checkout</label></div></details>`}
function serviceForm(r,i){return `<details class="am-admin-card" data-index="${i}" data-kind="services" ${r.name?'':'open'}><summary class="am-summary"><span>${esc(r.name||'New service')}</span> <span class="am-tag">${r.reviewed&&r.active?'Verified':'Review required'}</span>${deleteControl('services',r)}</summary><div class="am-form-grid">${field('name','Name',r.name,'text','required maxlength="120"')}<label class="am-field">Type<select name="kind"><option value="event" ${r.kind==='event'?'selected':''}>Event · flat package</option><option value="dining" ${r.kind==='dining'?'selected':''}>Dining · per guest</option></select></label>${textarea('description','Description and inclusions',r.description)}${field('price','Price (PHP)',r.price===null?'':r.price/100,'number','min="0" step="0.01" max="1000000"')}${field('capacity','Guest limit (event) / daily seats (dining)',r.capacity,'number','min="0" max="1000" step="1"')}<label class="am-field am-full">Upload event / dining pictures<input type="file" data-upload accept="image/*" multiple><small>Up to 12 photos; first photo appears on the public card. Optimized automatically.</small></label><div data-photos class="am-full">${photos(r)}</div><label class="am-checkbox"><input type="checkbox" name="active" ${r.active?'checked':''}> Visible to guests</label><label class="am-checkbox am-full"><input type="checkbox" name="reviewed" ${r.reviewed?'checked':''}> I have verified the price, capacity, and service availability for live bookings</label></div><p class="am-note">One event per day across the resort; dining capacity is shared across all reservations per venue per day. Requested times require staff confirmation.</p></details>`}
function receiptMarkup(b){
 if(b.hasReceipt){
  const url='/api/admin/receipt/'+encodeURIComponent(b.id);
  return '<div class="am-box"><strong>Payment receipt uploaded</strong><p><a href="'+url+'" target="_blank" rel="noopener noreferrer">View full receipt image</a></p><img src="'+url+'" loading="lazy" alt="Private payment receipt for '+esc(b.id)+'" style="display:block;max-width:240px;max-height:260px;object-fit:contain;border-radius:8px"></div>';
 }
 return b.reference?'<p>Legacy transfer reference: <strong>'+esc(b.reference)+'</strong></p>':'<p class="am-note">No payment receipt uploaded.</p>';
}
function bookings(){const counts=['awaiting_payment','payment_review','confirmed'].map(s=>`${model.bookings.filter(b=>b.status===s).length} ${s.replaceAll('_',' ')}`).join(' · ');return toolbar('Reservations',counts)+`<label class="am-field" style="max-width:240px;margin-bottom:15px">Filter by status<select id="booking-filter"><option value="all">All reservations</option>${['awaiting_payment','payment_review','confirmed','cancelled','expired'].map(s=>`<option value="${s}">${s.replaceAll('_',' ')}</option>`).join('')}</select></label>`+(!model.bookings.length?'<div class="am-admin-card">No reservations yet.</div>':model.bookings.map(b=>`<details class="am-admin-card" data-booking-status="${esc(b.status)}"><summary>${esc(b.id)} · ${esc(b.guest.name)} · ${money(b.total)} <span class="am-admin-status">${esc(b.status.replaceAll('_',' '))}</span></summary><div class="am-form-grid"><div><h3>Guest information</h3><div class="am-guest-details"><strong>${esc(b.guest.name)}</strong><span>${esc(b.guest.email)}</span><span>${esc(b.guest.phone)}</span><p style="white-space:pre-wrap">Requests: ${esc(b.guest.requests||'None')}</p></div></div><div><h3>Stay details</h3><p>${b.rooms.length?esc(b.checkin)+' to '+esc(b.checkout)+' · '+b.nights+' night(s)':'No overnight stay'}</p><p>Created: ${esc(phDate(b.created))}</p><p>Bookings are first-come, first-served. Unpaid requests do not hold inventory.</p><p>Payment required: <strong>${money(b.dueNow??b.total)}</strong> (${b.paymentPercent===50?'50% deposit':'100%'})</p>${receiptMarkup(b)}</div></div>${[...b.rooms,...b.addons,...(b.services||[])].map(l=>`<div class="am-line"><div>${esc(l.name)} × ${l.qty}${l.kind?` · ${esc(l.date)} at ${esc(l.time)} Philippine time${l.occasion?' · '+esc(l.occasion):''}`:''}${l.guests?` · ${l.guests} guest(s)`:''}</div><strong>${money(l.total)}</strong></div>`).join('')}<div class="am-total"><span>Total</span><span>${money(b.total)}</span></div><div class="am-box"><p class="am-note">${b.payment.method==='gcash'?'GCash':'Local bank transfer'} · Account recorded when booked</p>${esc(b.payment.bank)} · ${esc(b.payment.name)} · ${esc(b.payment.number)}</div><div class="am-form-actions">${(['awaiting_payment','payment_review'].includes(b.status)&&(b.hasReceipt||b.reference))?`<button class="am-primary" data-status="confirmed" data-id="${esc(b.id)}">Confirm verified payment</button>`:''}${['awaiting_payment','payment_review','confirmed'].includes(b.status)?`<button class="am-danger" data-status="cancelled" data-id="${esc(b.id)}">Cancel reservation</button>`:''}</div></details>`).join(''))}
function render(){if(!model)return;const more=$('#admin-more-nav');if(more)more.open=['services','addons','messages'].includes(tab);$$('[data-tab]').forEach(x=>{x.classList.toggle('selected',x.dataset.tab===tab);x.setAttribute('aria-current',x.dataset.tab===tab?'page':'false')});if(model.sectionErrors?.[tab]){const err=model.sectionErrors[tab];area.innerHTML=toolbar('Section temporarily unavailable','Other dashboard tabs can still be used. No data in this section has been replaced.')+`<div class="am-admin-card"><p class="am-error">${esc(err.error)}</p><p class="am-note">${esc(err.code||'')}</p><button class="am-secondary" data-refresh>Retry loading section</button></div>`;return;}if(tab==='rooms')area.innerHTML=toolbar('Rooms & prices','Tap a room to change its price, photos or availability. All changes stay here until you save.','+ Add room','Save all changes')+model.rooms.map(roomForm).join('');else if(tab==='services')area.innerHTML=toolbar('Events & dining','Verify example prices and actual capacity before enabling live reservations. Dining prices are per person; event rates are per occasion.','Add service','Save all services')+model.services.map(serviceForm).join('');else if(tab==='addons')area.innerHTML=toolbar('Optional extras','Starter extras are examples and disabled. Edit them, confirm the services and enable approved extras before saving.','Add extra','Save all extras')+(model.addons.length?model.addons.map(addonForm).join(''):'<div class="am-admin-card">No extras configured. Create an extra to list it in the guest checkout.</div>');else if(tab==='payment'){const p=model.payment;const bankReady=Boolean(p.bank?.trim()&&p.name?.trim()&&p.number?.trim()),gcashReady=Boolean(p.gcashName?.trim()&&p.gcashNumber?.trim());area.innerHTML=toolbar('Payment accounts','Set up GCash and local bank transfer separately. Guests only see complete payment methods. Each method has its own Save button.')+`<div class="am-payment-admin-grid"><form id="bank-settings" class="am-admin-card am-payment-card"><div class="am-payment-card-heading"><span class="am-pay-symbol">₱</span><div><h3>Local bank transfer</h3><small>${bankReady?'✓ Ready for guests':'Add account details to activate'}</small></div></div>${field('bank','Bank name',p.bank,'text','maxlength="150" placeholder="e.g. BDO"')}${field('name','Account holder name',p.name,'text','maxlength="150"')}${field('number','Bank account number',p.number,'text','maxlength="150"')}${textarea('instructions','Instructions (optional)',p.instructions)}<div class="am-payment-actions"><button type="submit" class="am-primary">Save bank details</button></div></form><form id="gcash-settings" class="am-admin-card am-payment-card"><div class="am-payment-card-heading"><span class="am-pay-symbol">G</span><div><h3>GCash</h3><small>${gcashReady?'✓ Ready for guests':'Add GCash details to activate'}</small></div></div>${field('gcashName','GCash account name',p.gcashName||'','text','maxlength="150"')}${field('gcashNumber','GCash mobile number',p.gcashNumber||'','tel','maxlength="40" placeholder="09XXXXXXXXX"')}${textarea('gcashInstructions','Instructions (optional)',p.gcashInstructions||'')}<div class="am-payment-actions"><button type="submit" class="am-primary">Save GCash details</button></div></form></div><p class="am-simple-help">Save each payment method separately. To disable one, clear its account fields and save that method. Existing reservations keep their previous account details.</p>`}else if(tab==='messages')area.innerHTML=toolbar('Contact messages','Messages submitted through the website contact form.')+(model.messages.length?model.messages.map(m=>`<details class="am-admin-card"><summary>${esc(m.name)} · ${esc(phDate(m.created))}</summary><p>${esc(m.email)}</p><pre>${esc(m.message)}</pre></details>`).join(''):'<div class="am-admin-card">No messages yet.</div>');else{area.innerHTML=bookings();$('#booking-filter')?.addEventListener('change',e=>$$('[data-booking-status]').forEach(x=>x.hidden=e.target.value!=='all'&&e.target.value!==x.dataset.bookingStatus))}}
function copyDrafts(){if(!['rooms','addons','services'].includes(tab))return;$$('[data-index]',area).forEach(el=>{let r=model[tab][Number(el.dataset.index)];$$('input[name],textarea[name],select[name]',el).forEach(input=>{let val=input.type==='checkbox'?input.checked:input.value;if(input.name==='price')val=val===''?null:Math.round(Number(val)*100);if(['capacity','inventory'].includes(input.name))val=Number(val);if(input.name==='amenities')val=val.split('\n').map(s=>s.trim()).filter(Boolean);r[input.name]=val})})}
function restoreOpen(index){const el=$(`[data-index="${index}"]`,area);if(el)el.open=true}
async function optimizePhoto(file){
 if(!['image/jpeg','image/png','image/webp','image/heic','image/heif'].includes(file.type))throw Error('Choose a JPG, PNG or WebP photo.');
 if(file.size>30_000_000)throw Error('Choose a photo under 30 MB.');
 const bitmap=typeof createImageBitmap==='function'?await createImageBitmap(file):await new Promise((resolve,reject)=>{const url=URL.createObjectURL(file),img=new Image();img.onload=()=>{URL.revokeObjectURL(url);resolve(img)};img.onerror=()=>{URL.revokeObjectURL(url);reject(Error('Cannot open this photo. Try JPG or PNG.'))};img.src=url});
 try{
  let max=1800,quality=.84;
  for(let pass=0;pass<6;pass++){
   const scale=Math.min(1,max/Math.max(bitmap.width,bitmap.height));
   const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));
   const ctx=canvas.getContext('2d',{alpha:false});ctx.fillStyle='#ffffff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);
   let blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/webp',quality));
   if(!blob||blob.type!=='image/webp')blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',quality));
   canvas.width=canvas.height=0;
   if(!blob)throw Error('Unable to process this image. Try a different photo.');
   if(blob.size<=1_500_000)return blob;
   max=Math.max(700,Math.round(max*.82));quality=Math.max(.58,quality-.06);
  }
  throw Error('Photo could not be compressed to the upload limit.');
 }finally{bitmap.close?.()}
}
async function upload(file){
 let blob;
 try{blob=await optimizePhoto(file)}catch(e){if(e?.name==='InvalidStateError'||e?.name==='NotSupportedError')throw Error('This photo format is not supported by your browser. Try JPG or PNG.');throw e}
 const data=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(Error('Cannot read the image.'));r.readAsDataURL(blob)});
 return (await api('upload','POST',{data})).url;
}
area.addEventListener('input',e=>{
 if(e.target.matches('input,textarea,select')&&e.target.id!=='booking-filter')dirty=true;
 if(e.target.name==='price'&&e.target.closest('[data-kind="rooms"]')){
  const card=e.target.closest('[data-index]');
  const preview=card.querySelector('[data-price-preview]');
  const amount=Number(e.target.value);
  if(preview)preview.textContent=e.target.value!==''&&Number.isFinite(amount)&&amount>=0?money(Math.round(amount*100)):'Add price';
 }
});
area.addEventListener('change',e=>{if(!e.target.matches('[data-upload]'))return;const el=e.target,files=[...el.files];run(async()=>{const card=el.closest('[data-index]'),idx=Number(card.dataset.index),kind=card.dataset.kind||tab;copyDrafts();const r=model[kind][idx];r.images=Array.isArray(r.images)?r.images:[];try{const limit=kind==='rooms'?15:12;if(files.length+r.images.length>limit)throw Error('Maximum '+limit+' photos for this '+(kind==='rooms'?'villa':'event / dining option')+'.');for(let i=0;i<files.length;i++){notice('Optimizing and uploading image '+(i+1)+' of '+files.length+'…');const url=await upload(files[i]);r.images.push(url);dirty=true;$('[data-photos]',card).innerHTML=photos(r)}notice('Photos uploaded. Click '+(kind==='rooms'?'Save room':'Save all services')+' to publish them.')}finally{el.value='';$('[data-photos]',card).innerHTML=photos(r)}})});
area.addEventListener('submit',e=>{if(!['bank-settings','gcash-settings'].includes(e.target.id))return;e.preventDefault();const f=e.target,method=f.id==='bank-settings'?'bank':'gcash',otherId=method==='bank'?'gcash-settings':'bank-settings';const values={...Object.fromEntries(new FormData(f)),method};const otherValues=Object.fromEntries(new FormData($('#'+otherId)));const otherHasUnsaved=Object.entries(otherValues).some(([key,val])=>val!==String(model.payment[key]??''));run(async()=>{applySaved('payment',await api('payment','PUT',values,model.revisions.payment),method==='bank'?'Bank details saved. Guests can now select bank transfer if the account is complete.':'GCash details saved. Guests can now select GCash if the account is complete.');if(otherHasUnsaved){const other=$('#'+otherId);for(const [key,val] of Object.entries(otherValues)){const input=other?.elements.namedItem(key);if(input)input.value=val;}dirty=true;notice('Saved '+(method==='bank'?'bank':'GCash')+' details. Your unsaved '+(method==='bank'?'GCash':'bank')+' entries are still here; click their Save button too.')}})});
area.addEventListener('click',e=>{const b=e.target.closest('button');if(!b||b.type==='submit'&&b.closest('form'))return;if(b.matches('[data-delete]')){e.preventDefault();e.stopPropagation()}run(async()=>{
 if(b.matches('[data-refresh]')){if(dirty&&!confirm('Discard unsaved changes?'))return;if(!model){await loadDashboard();return}await refresh();notice(model.sectionErrors?.[tab]?'':'Dashboard refreshed.',model.sectionErrors?.[tab]?.error||'')}
 else if(b.matches('[data-add]')){copyDrafts();const id=(tab==='rooms'?'villa-':tab==='services'?'service-':'extra-')+crypto.getRandomValues(new Uint32Array(2)).join('-');const obj=tab==='rooms'?{id,name:'',category:'',description:'',price:null,capacity:0,inventory:0,bed:'',size:'',amenities:[],images:[],active:true,policy:'',reviewed:false}:tab==='services'?{id,name:'',kind:'event',description:'',price:null,capacity:0,images:[],active:true,reviewed:false}:{id,name:'',description:'',price:null,basis:'stay',active:true};model[tab].push(obj);dirty=true;render();restoreOpen(model[tab].length-1)}
 else if(b.matches('[data-save]')){const invalid=$$('input,textarea,select',area).find(el=>!el.checkValidity());if(invalid){const card=invalid.closest('details');if(card)card.open=true;throw Error('Check '+(invalid.closest('label')?.textContent.trim()||invalid.name)+': '+invalid.validationMessage)}copyDrafts();applySaved(tab,await api(tab,'PUT',{items:model[tab]},model.revisions[tab]),tab==='rooms'?'Saved successfully — room prices are now updated on the website.':'Changes saved. Your website is updated.')}
 else if(b.matches('[data-delete]')){
  e.preventDefault();e.stopPropagation();
  const el=b.closest('[data-index]'),kind=el.dataset.kind||tab,idx=Number(el.dataset.index),item=model[kind][idx];
  if(!item)throw Error('This listing is no longer available. Refresh the dashboard.');
  const saved=isSaved(kind,item.id);
  if(saved){
   if(dirty)throw Error('Save or discard your other unsaved edits before deleting. Nothing has been deleted.');
   if(!confirm('Permanently remove "'+item.name+'" from the public catalog now? Future guests will no longer be able to book it. Existing reservations are kept.'))return;
   const result=await api('delete-item','DELETE',{section:kind,id:item.id},model.revisions[kind]);
   applySaved(kind,result,'Deleted "'+item.name+'" from the catalog. Existing reservations were kept.');
  }else{
   if(!confirm('Discard this unsaved '+(kind==='rooms'?'villa':kind==='services'?'service':'extra')+'?'))return;
   copyDrafts();
   for(const url of item.images||[])if(url.startsWith('/api/photo/')){
    try{await api('discard-photo','DELETE',{url})}catch(ex){if(ex.status!==409)throw ex}
   }
   model[kind].splice(idx,1);dirty=true;render();notice('Unsaved draft discarded. Save your remaining edits when ready.');
  }
 }
 else if(b.matches('[data-remove-photo],[data-cover-photo]')){
  e.preventDefault();
  const el=b.closest('[data-index]'),kind=el.dataset.kind||tab,idx=Number(el.dataset.index),item=model[kind][idx];
  if(!item)throw Error('This listing is no longer available. Refresh and retry.');
  const index=Number(b.dataset.removePhoto??b.dataset.coverPhoto),url=item.images?.[index];
  if(!url)throw Error('Photo not found. Refresh and retry.');
  if(b.matches('[data-cover-photo]')){
   copyDrafts();item.images.unshift(item.images.splice(index,1)[0]);dirty=true;$('[data-photos]',el).innerHTML=photos(item);notice('Cover selected. Click Save room (or Save all services) to publish it.');return;
  }
  const persisted=isSaved(kind,item.id)&&committed[kind].find(x=>x.id===item.id)?.images?.includes(url);
  if(persisted){
   if(dirty)throw Error('Save or discard your unsaved edits before deleting a saved photo. Nothing has been deleted.');
   if(!confirm('Delete this photo from "'+item.name+'" now? It will disappear from the public listing.'))return;
   const result=await api('delete-photo','DELETE',{section:kind,id:item.id,url},model.revisions[kind]);
   applySaved(kind,result,'Photo deleted from "'+item.name+'" and the public listing.');
  }else{
   if(!confirm('Remove this not-yet-published picture from the draft?'))return;
   if(url.startsWith('/api/photo/'))await api('discard-photo','DELETE',{url});
   copyDrafts();item.images.splice(index,1);dirty=true;$('[data-photos]',el).innerHTML=photos(item);notice('Photo removed from the draft.');
  }
 }
 else if(b.matches('[data-status]')){const s=b.dataset.status;if(!confirm(s==='confirmed'?'Confirm only after independently verifying the transfer against the resort bank account. Continue?':'Cancel this reservation and release its inventory?'))return;const result=await api('status','POST',{id:b.dataset.id,status:s});model.bookings=model.bookings.map(r=>r.id===result.booking.id?result.booking:r);render();notice('Reservation status updated.')}
 })});
$$('[data-tab]').forEach(b=>b.addEventListener('click',()=>run(()=>go(b.dataset.tab))));
$('#login-form').addEventListener('submit',e=>{e.preventDefault();const f=e.target;const values=Object.fromEntries(new FormData(f));run(async()=>{try{const result=await api('login','POST',values);f.reset();if(result?.version!==ADMIN_VERSION)throw new RequestError('The hosting service is running an outdated admin backend. Redeploy the backend and public files together.');authLoading('Confirming your sign-in…');try{await readSession()}catch(x){if(isSessionFailure(x)){loginMode('Sign-in was accepted, but the session cookie was not returned by your browser or hosting proxy. Open the same website address, allow first-party cookies and check that the proxy forwards Set-Cookie.');return;}authLoading(x.message,true);return;}await loadDashboard()}catch(x){loginMode(x.message);}})});
$('#logout').addEventListener('click',()=>run(async()=>{if(dirty&&!confirm('Sign out and discard unsaved changes?'))return;await api('logout','POST',{});dirty=false;model=null;tab='rooms';area.innerHTML='';notice();loginMode('Signed out.');}));
$('#retry-session').addEventListener('click',()=>run(restoreSession));
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue=''}});
run(restoreSession);
window.setInterval(heartbeat,300000);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')heartbeat()});
