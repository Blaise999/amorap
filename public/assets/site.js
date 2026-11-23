'use strict';
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const money=v=>new Intl.NumberFormat('en-PH',{style:'currency',currency:'PHP'}).format(v/100);
async function api(path,body){const res=await fetch('/api/'+path,{signal:AbortSignal.timeout(18000),method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});let data;try{data=await res.json()}catch{throw Error('Online reservation service is unavailable. Please try again later.')}if(!res.ok)throw Error(data.error||'Could not complete request.');return data;}
const fromStore=(k,v)=>{try{return JSON.parse(sessionStorage.getItem(k))||v}catch{return v}};
const toStore=(k,v)=>{try{sessionStorage.setItem(k,JSON.stringify(v))}catch{}};
let viewVersion=0;
let cart=fromStore('amora-cart-v1',{checkin:'',checkout:'',rooms:[],addons:[]}),lastBooking=fromStore('amora-last-v1',null),catalog=null,selected=null,focusBefore=null,quote=null;
function dateInPH(offset=0){const now=new Date(Date.now()+8*3600*1000+offset*864e5);return now.toISOString().slice(0,10)}
cart.services=Array.isArray(cart.services)?cart.services:[];if(!cart.checkin||cart.checkin<dateInPH()){cart.checkin=dateInPH();cart.checkout=dateInPH(1)}
function persist(){quote=null;toStore('amora-cart-v1',cart);$$('[data-cart-count]').forEach(el=>el.textContent=(cart.rooms.reduce((a,r)=>a+r.qty,0)+cart.services.length)||'');}
function error(e){const el=$('[data-error]',modal);if(el)el.textContent=e.message||String(e)}
function localCatalog(){return structuredClone(window.AMORAP_DEFAULT_CATALOG)}
let catalogRequest=null;
async function load(){
 if(catalogRequest)return catalogRequest;
 catalogRequest=(async()=>{
  try{
   const response=await fetch('/api/catalog',{cache:'no-store',signal:AbortSignal.timeout(6500)});
   if(!response.ok)throw Error('Catalog unavailable');
   const data=await response.json();
   if(!Array.isArray(data.rooms)||!Array.isArray(data.addons)||!Array.isArray(data.services))throw Error('Invalid catalog');
   catalog=data;
  }catch{
   // A momentary network error must never silently replace a confirmed rate
   // with an unrelated illustrative default rate.
   if(catalog&&!offline())catalog={...catalog,stale:true};
   else if(!catalog)catalog=localCatalog();
  }
  return catalog;
 })();
 try{return await catalogRequest}finally{catalogRequest=null}
}
const resortPhoto=url=>typeof url==='string'&&url.startsWith('/assets/villas/');
const photoLabel=(r,url)=>resortPhoto(url)?r.category+' resort setting':r.name;
const offline=()=>catalog?.fallback||catalog?.preview||catalog?.stale;

const modal=document.createElement('div');modal.className='am-modal';modal.hidden=true;modal.innerHTML='<section class="am-panel" role="dialog" aria-modal="true" aria-labelledby="am-modal-title"><div class="am-panel-header"><div><span class="am-kicker">AMORAP · DIRECT RESERVATIONS</span><h2 id="am-modal-title">Your stay</h2></div><button class="am-close" data-close aria-label="Close reservation">×</button></div><div class="am-panel-content" id="am-content"></div></section>';document.body.append(modal);
const content=$('#am-content');
function show(title,html,drawer=false){viewVersion++;const nav=$('.am-mobile-nav');if(nav){nav.hidden=true;$('[aria-label="Toggle menu"]')?.setAttribute('aria-expanded','false');}if(modal.hidden)focusBefore=document.activeElement;modal.classList.toggle('am-drawer',drawer);$('#am-modal-title').textContent=title;content.innerHTML=html;modal.hidden=false;document.body.style.overflow='hidden';content.scrollTop=0;$('.am-close',modal).focus({preventScroll:true});}
function close(){viewVersion++;modal.hidden=true;document.body.style.overflow='';focusBefore?.focus({preventScroll:true})}
function steps(step){return `<div class="am-stepbar">${['Dates','Room & details','Checkout','Payment'].map((s,i)=>`<span class="${i===step?'active':''}">${i+1}. ${s}</span>`).join('')}</div>`}

let datedRoomStock=null;
async function fetchDatedRoomStock(){
 datedRoomStock=null;
 if(offline())return;
 try{
  const query=new URLSearchParams({checkin:cart.checkin,checkout:cart.checkout});
  const response=await fetch('/api/availability?'+query.toString(),{cache:'no-store',signal:AbortSignal.timeout(12000)});
  if(!response.ok)throw Error('Availability temporarily unavailable');
  const data=await response.json();
  if(data.checkin!==cart.checkin||data.checkout!==cart.checkout||!Array.isArray(data.rooms))throw Error('Availability dates did not match');
  datedRoomStock=data;
 }catch{datedRoomStock=null}
}
function freeCount(room){
 if(datedRoomStock?.checkin!==cart.checkin||datedRoomStock?.checkout!==cart.checkout)return null;
 const result=datedRoomStock.rooms.find(x=>x.id===room.id);
 return Number.isInteger(result?.available)&&result.available>=0?result.available:null;
}
function roomCountLabel(room,dated=false){
 if(dated){
  const n=freeCount(room);
  return n===null?'Live date availability unavailable — final count checked at checkout':n===0?'0 rooms available for selected dates — fully booked':n+' room'+(n===1?'':'s')+' available for selected dates';
 }
 if(offline())return 'Live room counts temporarily unavailable — select dates to check';
 const n=Math.max(0,Number(room.inventory)||0);
 return n+' room'+(n===1?'':'s')+' of this type · Choose dates for live availability';
}
function roomStockBadge(room,dated=false){
 const n=dated?freeCount(room):null;
 return '<p class="am-room-stock'+(dated&&n===0?' is-soldout':'')+'" aria-live="polite">'+esc(roomCountLabel(room,dated))+'</p>';
}
function roomIsOpen(room,dated=false){
 return planRoom(room)&&(!dated||freeCount(room)!==0);
}
function card(r,dated=false){const canBook=roomIsOpen(r,dated);return `<article class="am-room-card"><div class="am-room-image">${r.images.length?`<img loading="lazy" src="${esc(r.images[0])}" alt="${esc(photoLabel(r,r.images[0]))}">${resortPhoto(r.images[0])?'<small class="am-resort-caption">Resort setting</small>':''}`:'<span>Villa photos to be updated</span>'}</div><div class="am-room-body"><span class="am-kicker">${esc(r.category)}</span><h3>${esc(r.name)}</h3><p>${esc(r.description)}</p><div class="am-room-meta">${[r.capacity?`${r.capacity} guests`:'',r.bed,r.size,...r.amenities].filter(Boolean).map(x=>`<span>${esc(x)}</span>`).join('')}</div>${r.policy?`<p class="am-note">${esc(r.policy)}</p>`:''}<p class="am-note">${r.bedrooms||1}BR · Up to ${r.maxKids??2} children under ${r.freeChildUnderAge??12} stay free · ${r.petsAllowed?'Pets allowed with resort rules':'No pets'}</p>${roomStockBadge(r,dated)}${r.images.length>1?`<div class="am-room-gallery">${r.images.map((im,i)=>`<button data-photo="${esc(im)}" type="button" aria-label="Show photo ${i+1}"><img src="${esc(im)}" alt="Villa photo ${i+1}"></button>`).join('')}</div>`:''}<div class="am-card-end"><div><strong>${r.price===null?'Rate to be confirmed':money(r.price)}</strong>${r.price!==null?`<small> / night${r.reviewed===false?' · indicative rate':''}</small>`:''}</div><button class="am-primary" data-room="${esc(r.id)}" ${canBook?'':'disabled'}>${canBook?'Book this villa':dated&&freeCount(r)===0?'Fully booked for dates':'Awaiting availability confirmation'}</button></div></div></article>`}
const planRoom=r=>r?.bookable===true&&r.price>0&&r.capacity>0&&r.inventory>0;
const planService=r=>r?.bookable===true&&r.price>0&&r.capacity>0;
const villaSelection={};
function renderCatalog(){const root=$('#villa-catalog');if(!root||!catalog)return;if(!root.classList.contains('am-villa-sections')){root.innerHTML=catalog.rooms.map(card).join('')||'<p>No villas available at present.</p>';return}const grouped=new Map();for(const r of catalog.rooms){const category=r.category||'Villas';if(!grouped.has(category))grouped.set(category,[]);grouped.get(category).push(r)}
root.innerHTML=[...grouped.entries()].map(([category,rooms],index)=>{const r=rooms.find(x=>x.id===villaSelection[category])||rooms[0];const photo=r.images[0];const meta=[r.capacity?`${r.capacity} guests`:'',r.bed,r.size,...r.amenities].filter(Boolean);
return `<article class="am-villa-section ${index%2?'am-villa-reverse':''}"><figure class="am-villa-figure">${photo?`<img src="${esc(photo)}" alt="${esc(photoLabel(r,photo))}"><figcaption ${resortPhoto(photo)?'':'hidden'}>Resort setting · room-specific gallery to be confirmed</figcaption>`:'<div class="am-villa-no-photo">'+esc(category)+'</div>'}${r.images.length>1?`<div class="am-villa-gallery">${r.images.map((im,i)=>`<button type="button" data-villa-photo="${esc(im)}" aria-label="View photo ${i+1}"><img src="${esc(im)}" alt="${esc(photoLabel(r,im))}"></button>`).join('')}</div>`:''}</figure><div class="am-villa-copy"><h2>${esc(category)}</h2><div class="am-villa-rule"></div><p>${esc(r.description)}</p><div class="am-villa-tabs" aria-label="Villa types">${rooms.map(x=>`<button type="button" class="${x.id===r.id?'selected':''}" aria-pressed="${x.id===r.id}" data-villa-tab="${esc(x.id)}">${esc(x.name.includes(' · ')?x.name.split(' · ').at(-1):x.name)}</button>`).join('')}</div><h3>${esc(r.name)}</h3>${meta.length?`<div class="am-room-meta">${meta.map(x=>`<span>${esc(x)}</span>`).join('')}</div>`:''}${r.policy?`<p class="am-note">${esc(r.policy)}</p>`:''}${roomStockBadge(r)}<div class="am-villa-book"><strong>${r.price===null?'Rate to be confirmed':money(r.price)+' / night'+(r.reviewed===false?' (indicative)':'')}</strong><button type="button" class="am-primary" data-room="${esc(r.id)}" ${planRoom(r)?'':'disabled'}>${planRoom(r)?'Book this villa':'Awaiting availability confirmation'}</button></div></div></article>`}).join('')||'<p>Villas are being updated. Please check back.</p>';const status=$('#villa-status');if(status)status.textContent=offline()?'You are viewing the resort catalog. You can choose dates and add villas to your cart. Live availability and payment are temporarily unavailable.':'';}

function serviceCard(r){return `<article class="am-room-card">${Array.isArray(r.images)&&r.images.length?`<div class="am-room-image"><img loading="lazy" src="${esc(r.images[0])}" alt="${esc(r.name)}"></div>`:''}<div class="am-room-body"><span class="am-kicker">${r.kind==='event'?'Events':'Dining'}</span><h3>${esc(r.name)}</h3><p>${esc(r.description)}</p><div class="am-room-meta"><span>Up to ${r.capacity} guests</span></div><div class="am-card-end"><div><strong>${r.price===null?'Rate to be confirmed':money(r.price)}</strong><small> / ${r.kind==='event'?'event':'person'}${r.reviewed?'':' · indicative'}</small></div><button type="button" class="am-primary" data-service="${esc(r.id)}" ${planService(r)?'':'disabled'}>${planService(r)?`Book ${r.kind==='event'?'event':'dining'}`:'Awaiting availability confirmation'}</button></div></div></article>`}
function renderServices(){if(!catalog)return;const services=catalog.services||[];const ev=$('#event-catalog'),dining=$('#dining-catalog');if(ev)ev.innerHTML=services.filter(r=>r.kind==='event').map(serviceCard).join('')||'<p>No event packages are currently listed.</p>';if(dining)dining.innerHTML=services.filter(r=>r.kind==='dining'&&!['dining-cafe','dining-welcome','dining-garden'].includes(r.id)).map(serviceCard).join('');$$('[data-service-rate]').forEach(el=>{let r=services.find(x=>x.id===el.dataset.serviceRate&&x.kind==='dining');el.textContent=r&&r.price!==null?money(r.price)+' per person'+(r.reviewed?'':' (indicative)'):'Rate to be confirmed'});$$('[data-service]',document).filter(el=>!modal.contains(el)).forEach(el=>{let r=services.find(x=>x.id===el.dataset.service&&(el.closest('.am-room-card')||x.kind==='dining'));el.disabled=!planService(r);const block=el.closest('[data-dining-card]');if(block&&r){const h=block.querySelector('h3'),d=block.querySelector('[data-dining-description]');if(h)h.textContent=r.name;if(d)d.textContent=r.description;const img=block.querySelector('img');if(img&&r.images?.length){img.src=r.images[0];img.alt=r.name;}block.hidden=false}else if(block&&!r)block.hidden=true})}
function renderAll(){renderCatalog();renderServices()}
function beginBooking(roomId=null){
 const c=catalog||localCatalog();catalog=c;
 const preset=roomId&&c.rooms.find(r=>r.id===roomId);
 show('Choose your dates',steps(0)+`<p>${preset?'Select your travel dates before booking '+esc(preset.name)+'.':'First select your travel dates, then choose your villa.'}</p>${preset?`<div class="am-price-persistent"><span>${esc(preset.name)} · nightly rate</span><strong>${preset.price!==null?money(preset.price):'Price being confirmed'}</strong>${offline()?'<small>Indicative rate — final price confirmed at checkout</small>':''}</div>`:''}<form id="am-dates-form"><div class="am-form-grid"><label class="am-field">Check-in date<input type="date" name="checkin" min="${dateInPH()}" max="${dateInPH(730)}" value="${esc(cart.checkin)}" required></label><label class="am-field">Check-out date<input type="date" name="checkout" min="${dateInPH(1)}" value="${esc(cart.checkout)}" required></label></div><p class="am-note">All villas in your reservation share the same arrival and departure dates. You can change the dates before checkout.</p><div class="am-error" data-error role="alert"></div><div class="am-form-actions"><button class="am-primary" type="submit">Continue to villas →</button></div></form>`);
 const f=$('#am-dates-form');const ci=f.elements.checkin,co=f.elements.checkout;
 const adjust=()=>{if(!ci.value)return;const d=new Date(ci.value+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+1);co.min=d.toISOString().slice(0,10);if(co.value<=ci.value)co.value=co.min};
 ci.addEventListener('change',adjust);adjust();
 f.addEventListener('submit',async e=>{e.preventDefault();if(!f.reportValidity())return;const nights=Math.round((new Date(co.value)-new Date(ci.value))/864e5);if(nights<1||nights>60){error(Error('Choose a stay between 1 and 60 nights.'));return}cart.checkin=ci.value;cart.checkout=co.value;persist();if(roomId){show('Checking room availability',steps(1)+'<p>Checking rooms available for your dates…</p>');const version=viewVersion;await fetchDatedRoomStock();if(version===viewVersion)configure(roomId)}else choose('villa')});
}
async function choose(kind='all'){show('Choose your reservation',steps(1)+'<p>Checking current rates and availability…</p>');const version=viewVersion;await load();if(version!==viewVersion)return;await fetchDatedRoomStock();if(version!==viewVersion)return;function contents(){let rooms=kind==='all'||kind==='villa'?catalog.rooms:[],services=(catalog.services||[]).filter(r=>kind==='all'||r.kind===kind);return steps(1)+`<div class="am-info am-dates-summary">Stay: <strong>${esc(cart.checkin)} — ${esc(cart.checkout)}</strong> <button type="button" class="am-link" data-dates>Change dates</button></div><div class="am-form-actions am-choice-tabs"><button class="am-secondary" data-service-kind="all">All</button><button class="am-secondary" data-service-kind="villa">Villas</button><button class="am-secondary" data-service-kind="event">Events</button><button class="am-secondary" data-service-kind="dining">Dining</button></div>${offline()?'<div class="am-info">Browse and plan your reservation. Live availability and payments require a working connection.</div>':''}<div class="am-grid">${rooms.map(r=>card(r,true)).join('')}${services.map(serviceCard).join('')||(!rooms.length?'<p>No options are currently listed.</p>':'')}</div><div class="am-form-actions"><button class="am-secondary" data-cart>View checkout (${cart.rooms.length+cart.services.length})</button></div>`}renderAll();show('Choose your reservation',contents());}
function configureService(id,editKey){const r=catalog?.services?.find(x=>x.id===id);if(!planService(r)){show('Reservation unavailable','<p>The resort has not yet approved this reservation option for online booking.</p><button class="am-secondary" data-book>Choose another option</button>');return}const existing=cart.services.find(x=>serviceKey(x)===editKey);const event=r.kind==='event';show(r.name,steps(1)+`<p>${esc(r.description)}</p><div class="am-info">${money(r.price)} per ${event?'event':'person'} · Up to ${r.capacity} guests${r.bookable?'':' · Estimated rate; live verification required'}</div><form id="am-service-form"><div class="am-form-grid"><label class="am-field">Reservation date<input type="date" name="date" min="${dateInPH()}" max="${dateInPH(730)}" value="${esc(existing?.date||dateInPH(1))}" required></label><label class="am-field">Preferred time (Philippine time)<input type="time" name="time" value="${esc(existing?.time||'12:00')}" required></label><label class="am-field">Number of guests<input type="number" name="guests" min="1" max="${r.capacity}" value="${existing?.guests||1}" required></label><label class="am-field">${event?'Type of occasion':'Occasion (optional)'}<input name="occasion" maxlength="150" value="${esc(existing?.occasion||'')}" placeholder="${event?'Wedding, birthday, business gathering…':'Birthday, lunch, dinner…'}" ${event?'required':''}></label></div><div id="am-service-estimate" class="am-total"></div><p class="am-note">The resort confirms venue details, availability and the requested time before confirming the reservation.</p><div class="am-error" data-error role="alert"></div><div class="am-form-actions"><button type="button" class="am-secondary" data-choose>Browse options</button><button class="am-primary" type="submit">${existing?'Update reservation':'Add to reservation'}</button></div></form>`);const form=$('#am-service-form');const update=()=>$('#am-service-estimate').innerHTML=`<span>Estimated total</span><span>${money(r.price*(event?1:Number(form.elements.guests.value)||0))}</span>`;form.addEventListener('input',update);update();form.addEventListener('submit',e=>{e.preventDefault();const v=Object.fromEntries(new FormData(form)),item={id,date:v.date,time:v.time,guests:Number(v.guests),occasion:v.occasion.trim()};if(event&&!item.occasion){error(Error('Enter the type of occasion.'));return}if(cart.services.some(x=>serviceKey(x)===serviceKey(item)&&serviceKey(x)!==editKey)){error(Error('This option is already in your reservation for that time.'));return}cart.services=cart.services.filter(x=>serviceKey(x)!==editKey);cart.services.push(item);persist();renderCart()})}
const serviceKey=x=>[x.id,x.date,x.time].join('|');
function configure(id){const r=catalog?.rooms.find(x=>x.id===id);if(r&&freeCount(r)===0){show('Fully booked','<p>There are <strong>0 rooms available</strong> for those dates. Choose another room type or different dates.</p><button class="am-secondary" data-book>Choose different dates</button>');return;}if(!planRoom(r)){show('Villa unavailable','<p>The resort has not yet approved this villa rate and inventory for online booking. Please check back after confirmation.</p><button class="am-secondary" data-book>Choose another villa</button>');return;}selected=id;const existing=cart.rooms.find(x=>x.id===id);const available=freeCount(r),maxRooms=Math.min(available===null?r.inventory:available,30);const bedrooms=r.bedrooms??(r.id.includes('double')?2:1),freeAge=r.freeChildUnderAge??12,maxKids=r.maxKids??(bedrooms>=2?4:2),petsAllowed=r.petsAllowed===true,maxPets=petsAllowed?(r.maxPets??0):0,petFee=r.petFee??0;show(r.name,steps(1)+`<p>${esc(r.description)}</p><div class="am-price-persistent"><span>Nightly price · per villa</span><strong>${money(r.price)}</strong><small>${bedrooms}BR · ${r.capacity} adults per villa · Up to ${maxKids} kids under ${freeAge} free${petsAllowed?` · ${maxPets} pets allowed`: ' · No pets'}${r.bookable?'':' · Indicative rate; final price confirmed at checkout'}</small>${roomStockBadge(r,true)}</div><form id="am-stay-form"><div class="am-form-grid"><label class="am-field">Check-in<input name="checkin" type="date" min="${dateInPH()}" value="${esc(cart.checkin)}" required></label><label class="am-field">Check-out<input name="checkout" type="date" min="${dateInPH(1)}" value="${esc(cart.checkout)}" required></label><label class="am-field">Number of villas (${available===null?'availability confirmed during checkout':available+' available for selected dates'})<input name="qty" type="number" min="1" max="${maxRooms}" value="${Math.min(existing?.qty||1,maxRooms)}" required></label><label class="am-field">Adults and guests aged ${freeAge}+<input name="guests" type="number" min="1" max="${r.capacity*(existing?.qty||1)}" value="${existing?.guests||1}" required></label><label class="am-field">Kids under ${freeAge} (free, max ${maxKids}/villa)<input name="kids" type="number" min="0" max="${maxKids*(existing?.qty||1)}" value="${existing?.kids||0}" required></label><label class="am-field">Pets (${petsAllowed?`max ${maxPets}/villa`:'not permitted'})<input name="pets" type="number" min="0" max="${maxPets*(existing?.qty||1)}" value="${petsAllowed?(existing?.pets||0):0}" ${petsAllowed?'':'disabled'}></label></div><p class="am-note">${maxKids} children younger than ${freeAge} can stay free in each ${bedrooms}BR villa. Children aged ${freeAge} and older count as regular guests.${petsAllowed?` Pet fee: ${money(petFee)} per pet per stay. ${esc(r.petPolicy||'')}`:' Pets are not allowed in this room.'}</p><div id="am-estimate" class="am-total"></div><p class="am-note">All rooms in this reservation use the same check-in and check-out dates. Availability is verified before checkout.</p><div class="am-error" data-error role="alert"></div><div class="am-form-actions"><button type="button" class="am-secondary" data-book>Choose another villa</button><button class="am-primary" type="submit">${existing?'Update':'Add to reservation'}</button></div></form>`);const f=$('#am-stay-form');function update(){const qty=Number(f.elements.namedItem('qty').value);f.elements.namedItem('guests').max=r.capacity*qty;f.elements.namedItem('kids').max=maxKids*qty;f.elements.namedItem('pets').max=maxPets*qty;const start=f.elements.namedItem('checkin').value,end=f.elements.namedItem('checkout').value;if(start){let d=new Date(start+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+1);f.elements.namedItem('checkout').min=d.toISOString().slice(0,10);if(end<=start)f.elements.namedItem('checkout').value=d.toISOString().slice(0,10)}const n=Math.round((new Date(f.elements.namedItem('checkout').value)-new Date(start))/864e5);$('#am-estimate').innerHTML=n>0&&qty>0?`<span>${n} night${n===1?'':'s'}</span><span>${money(n*qty*r.price+Number(f.elements.namedItem('pets').value||0)*petFee)}</span>`:''}f.addEventListener('input',update);update();f.addEventListener('submit',async e=>{e.preventDefault();const data=new FormData(f);cart.checkin=data.get('checkin');cart.checkout=data.get('checkout');cart.rooms=cart.rooms.filter(x=>x.id!==id);cart.rooms.push({id,qty:Number(data.get('qty')),guests:Number(data.get('guests')),kids:Number(data.get('kids')||0),pets:petsAllowed?Number(data.get('pets')||0):0});persist();renderCart()})}
function stayHeading(q){return q.rooms?.length?`<strong>${esc(q.checkin)} — ${esc(q.checkout)}</strong>`:''}
function quoteLines(q){return [...q.rooms,...q.addons,...(q.services||[])].map(l=>`<div class="am-line"><div><strong>${esc(l.name)}</strong><small>${l.kind?`${esc(l.date)} · ${esc(l.time)} · ${l.guests} guest(s)${l.occasion?' · '+esc(l.occasion):''}`:l.qty+' '+(l.guests?'villa(s) · '+l.guests+' adults'+(l.kids?' · '+l.kids+' kids':'')+(l.pets?' · '+l.pets+' pets':'')+' · '+q.nights+' night(s)':l.basis==='night'?'× '+q.nights+' night(s)':'extra(s)')}</small></div><strong>${money(l.total)}</strong></div>`).join('')}
function localEstimate(){const c=catalog||localCatalog();const nights=Math.max(0,Math.round((new Date(cart.checkout)-new Date(cart.checkin))/864e5)),rooms=cart.rooms.map(l=>{const r=c.rooms.find(x=>x.id===l.id);return {...l,name:r?.name||l.id,total:r?.price!=null?r.price*l.qty*nights+(r.petFee||0)*(l.pets||0):null}}),services=cart.services.map(l=>{const r=c.services.find(x=>x.id===l.id);return {...l,name:r?.name||l.id,total:r?.price!=null?r.price*(r.kind==='event'?1:l.guests):null}}),addons=cart.addons.map(l=>{const r=c.addons.find(x=>x.id===l.id);return {...l,total:r?.price!=null?r.price*l.qty*(r.basis==='night'?nights:1):null}});const all=[...rooms,...services,...addons];return {rooms,services,addons,total:all.every(l=>l.total!==null)?all.reduce((n,l)=>n+l.total,0):null}}
function cartPricePreview(){
 if(!cart.rooms.length&&!cart.services.length)return '';
 const estimate=localEstimate();
 if(estimate.total===null)return '<p class="am-note">Checking current prices…</p>';
 const nights=cart.rooms.length?Math.max(0,Math.round((new Date(cart.checkout)-new Date(cart.checkin))/864e5)):0;
 return `<div class="am-price-persistent am-checkout-price" role="status"><span>Estimated reservation total${nights?' · '+nights+' night'+(nights===1?'':'s'):''}</span><strong>${money(estimate.total)}</strong><small>Final rate and availability will be verified before reservation.</small></div>`;
}
async function renderCart(){const pending=cart.rooms.length||cart.services.length?cartPricePreview():'';show('Your reservation',steps(2)+'<p>Checking the final price and availability…</p>'+pending+'<div class="am-error" data-error role="alert"></div>',true);const version=viewVersion;try{await load();if(version!==viewVersion)return;if(!cart.rooms.length&&!cart.services.length){show('Your reservation',steps(2)+`<div class="am-empty"><h3>Your reservation is empty.</h3><p>Book a villa, dining or an event to begin.</p><button class="am-primary" data-book>Explore booking options</button></div>${lastBooking?'<button class="am-secondary" data-resume>View last reservation</button>':''}`,true);return}let q=null,err='';if(!offline()){try{q=await api('quote',cart);quote=q}catch(e){err=e.message}}else err='Live availability is unavailable. Your selection is saved in this browser; no reservation or payment has been made.';if(version!==viewVersion)return;const est=q||localEstimate();const displayedEstimate=localEstimate();const rateUpdated=Boolean(q&&displayedEstimate.total!==null&&displayedEstimate.total!==q.total);const amount=l=>l?.total==null?'—':money(l.total);const lines=cart.rooms.map(l=>{let r=catalog.rooms.find(x=>x.id===l.id);return `<div class="am-line"><div><strong>${esc(r?.name||l.id)}</strong><small>${l.qty} villa(s) · ${l.guests} adults${l.kids?' · '+l.kids+' kids':''}${l.pets?' · '+l.pets+' pets':''}</small>${planRoom(r)?`<button class="am-link" data-room="${esc(l.id)}">Edit</button> · `:''}<button class="am-link" data-remove="${esc(l.id)}">Remove</button></div><strong>${amount(est.rooms.find(x=>x.id===l.id))}</strong></div>`}).join('');const services=cart.services.map(l=>{const r=catalog.services.find(x=>x.id===l.id),key=serviceKey(l);return `<div class="am-line"><div><strong>${esc(r?.name||l.id)}</strong><small>${esc(l.date)} · ${esc(l.time)} · ${l.guests} guests${l.occasion?' · '+esc(l.occasion):''}</small>${planService(r)?`<button class="am-link" data-service="${esc(l.id)}" data-edit-service="${esc(key)}">Edit</button> · `:''}<button class="am-link" data-remove-service="${esc(key)}">Remove</button></div><strong>${amount(est.services.find(x=>serviceKey(x)===key))}</strong></div>`}).join('');const extras=cart.rooms.length?catalog.addons.map(a=>`<div class="am-line"><div><strong>${esc(a.name)}</strong><small>${esc(a.description)}</small><small>${money(a.price)} / ${a.basis==='night'?'night':'stay'}</small></div><label class="am-field">Qty<input class="am-control" aria-label="Quantity for ${esc(a.name)}" data-addon="${esc(a.id)}" type="number" min="0" max="99" value="${cart.addons.find(x=>x.id===a.id)?.qty||0}"></label></div>`).join(''):'';show('Your reservation',steps(2)+`<div class="am-box">${cart.rooms.length?`<strong>${esc(cart.checkin)} — ${esc(cart.checkout)}</strong>${lines}`:''}${services}<button class="am-link" data-book>Add another booking</button></div>${cart.rooms.length?`<h3>Personalize your stay</h3>${extras||'<p class="am-note">No additional services listed.</p>'}`:''}${cart.addons.length?`<button class="am-link" data-clear-extras>Clear extras</button>`:''}${est.total!==null?`<div class="am-total" data-reservation-total><span>${q?'Verified total':'Estimated total'} · PHP</span><span>${money(est.total)}</span></div>`:''}${rateUpdated?'<div class="am-info">Room prices were updated. Please review the new total before checkout.</div>':''}<div class="am-error" data-error role="alert">${esc(err)}</div>${!catalog.paymentReady?'<div class="am-info">Direct payment is not configured yet. Your selections can be saved, but checkout cannot be completed.</div>':''}<div class="am-form-actions"><button class="am-secondary" data-cart>Refresh availability</button><button class="am-primary" data-checkout ${q&&catalog.paymentReady?'':'disabled'}>Continue to checkout →</button></div>${lastBooking?'<p><button class="am-link" data-resume>View last reservation</button></p>':''}`,true)}catch(e){error(e)}}
const PAYMENT_POLICY='Bookings are strictly first-come, first-served. A 50% or 100% payment is required to secure your reservation. Unpaid bookings are not confirmed and remain subject to availability';
async function checkout(){show('Checkout',steps(2)+'<p>Verifying your reservation…</p>'+cartPricePreview()+'<div class="am-error" data-error role="alert"></div>',true);const version=viewVersion;try{const q=await api('quote',cart);if(version!==viewVersion)return;quote=q;await load();if(version!==viewVersion)return;const available=catalog.paymentMethods||[];const methodCards=['bank','gcash'].map(method=>`<label class="am-payment-option ${available.includes(method)?'':'is-disabled'}"><input type="radio" name="paymentMethod" value="${method}" ${available.includes(method)?'required':'disabled'}><span><strong>${method==='bank'?'Local bank transfer':'GCash'}</strong><small>${available.includes(method)?(method==='bank'?'Transfer to the resort bank account':'Send to the resort GCash account'):'Not configured yet by the resort'}</small></span></label>`).join('');show('Checkout',steps(2)+`<h3>Guest information</h3><form id="am-guest-form"><div class="am-form-grid"><label class="am-field am-full">Full name<input name="name" autocomplete="name" required maxlength="150"></label><label class="am-field">Email<input name="email" type="email" autocomplete="email" required maxlength="200"></label><label class="am-field">Phone number<input name="phone" type="tel" autocomplete="tel" required maxlength="70"></label><label class="am-field am-full">Special requests (optional)<textarea name="requests" maxlength="2000" placeholder="Arrival time, dietary requests, accessibility needs…"></textarea></label></div><div class="am-box">${stayHeading(q)}${quoteLines(q)}<div class="am-total"><span>Total</span><span>${money(q.total)}</span></div></div><h3>Choose how much to pay</h3><div class="am-payment-options"><label class="am-payment-option"><input type="radio" name="paymentPercent" value="50" checked required><span><strong>50% deposit</strong><small>Pay half now, with the remainder payable under the resort’s instructions</small></span></label><label class="am-payment-option"><input type="radio" name="paymentPercent" value="100" required><span><strong>100% payment</strong><small>Pay the full amount now</small></span></label></div><p class="am-note">Payment to send now: <strong data-due-now>${money(Math.ceil(q.total/2))}</strong></p><h3>Choose payment method</h3><div class="am-payment-options">${methodCards}</div><p class="am-note">${PAYMENT_POLICY}.</p><label class="am-field" style="display:flex;flex-direction:row;align-items:flex-start"><input type="checkbox" required style="width:18px;min-height:20px;flex:none"> I understand that confirmation is subject to payment verification.</label><div class="am-error" data-error role="alert"></div><div class="am-form-actions"><button type="button" class="am-secondary" data-cart>Back</button><button class="am-primary" type="submit" ${available.length?'':'disabled'}>Reserve & get payment instructions</button></div></form>`,true);$('#am-guest-form').addEventListener('change',e=>{if(e.target.name==='paymentPercent'){const percent=Number(e.target.value);const due=$('[data-due-now]',e.currentTarget);if(due)due.textContent=money(Math.ceil(q.total*percent/100));}});$('#am-guest-form').addEventListener('submit',async e=>{e.preventDefault();const f=e.currentTarget,b=f.querySelector('[type=submit]');b.disabled=true;try{const result=await api('bookings',{...cart,expectedTotal:q.total,paymentMethod:f.elements.namedItem('paymentMethod')?.value,paymentPercent:Number(f.elements.namedItem('paymentPercent')?.value),guest:Object.fromEntries(new FormData(f))});lastBooking={id:result.booking.id,token:result.token};toStore('amora-last-v1',lastBooking);cart.rooms=[];cart.addons=[];cart.services=[];persist();payment(result.booking)}catch(e){error(e);b.disabled=false}})}catch(e){error(e)}}
async function prepareReceipt(file){
 if(!file)throw Error('Please choose a receipt image.');
 if(file.size>25_000_000)throw Error('Choose an image under 25 MB; the browser will reduce it before upload.');
 const supported=['image/jpeg','image/png','image/webp','image/heic','image/heif'];
 if(!supported.includes(file.type))throw Error('Choose a JPG, PNG or WebP receipt image (or a phone photo that your browser can convert).');
 let blob=file;
 if(file.size>1_400_000||!['image/jpeg','image/png','image/webp'].includes(file.type)){
  let picture;let url;
  try{
   if(typeof createImageBitmap==='function')picture=await createImageBitmap(file);
   else{
    url=URL.createObjectURL(file);
    picture=await new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(Error('Could not open this image; try JPG or PNG.'));im.src=url});
   }
   let width=2100,quality=.91;
   for(let i=0;i<7;i++){
    const scale=Math.min(1,width/Math.max(picture.width,picture.height));
    const canvas=document.createElement('canvas');
    canvas.width=Math.round(picture.width*scale)||1;canvas.height=Math.round(picture.height*scale)||1;
    const context=canvas.getContext('2d',{alpha:false});
    context.fillStyle='#fff';context.fillRect(0,0,canvas.width,canvas.height);
    context.drawImage(picture,0,0,canvas.width,canvas.height);
    blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',quality));
    canvas.width=canvas.height=0;
    if(blob&&blob.size<=1_500_000)break;
    width=Math.max(900,Math.round(width*.83));quality=Math.max(.68,quality-.045);
   }
  }finally{picture?.close?.();if(url)URL.revokeObjectURL(url)}
 }
 if(!blob||blob.size>1_700_000)throw Error('Receipt is still too large. Please crop or take a smaller screenshot.');
 return await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Unable to read the receipt image.'));reader.readAsDataURL(blob)});
}
function payment(b){
 const p=b.payment,waiting=b.status==='awaiting_payment';
 const labels={awaiting_payment:'Awaiting receipt',payment_review:'Payment under review',confirmed:'Confirmed',cancelled:'Cancelled',expired:'Expired'};
 const percent=b.paymentPercent===50?50:100, due=b.dueNow??Math.ceil(b.total*percent/100);
 show('Payment & reservation',steps(3)+`<div class="am-info"><strong>${esc(labels[b.status]||b.status)}</strong><br>Reservation ${esc(b.id)}</div><div class="am-box">${stayHeading(b)}${quoteLines(b)}<div class="am-total"><span>Booking total</span><span>${money(b.total)}</span></div><div class="am-total"><span>${percent}% payment to submit</span><span>${money(due)}</span></div>${percent===50?`<p class="am-note">Remaining balance: ${money(b.total-due)}. Follow the resort's instructions for the balance.</p>`:''}</div><p class="am-note">${PAYMENT_POLICY}.</p>${waiting?`<h3>${p.method==='gcash'?'GCash':'Local bank transfer'}</h3><p>Send ${money(due)} via ${p.method==='gcash'?'GCash':'local bank transfer'} to the details below, then upload a clear payment receipt. This does not confirm your booking until the resort verifies payment and availability.</p><div class="am-box am-pay-data"><div><small>${p.method==='gcash'?'Payment provider':'Bank'}</small><strong>${esc(p.bank)}</strong></div><span></span><div><small>Account holder</small><strong>${esc(p.name)}</strong></div><span></span><div><small>${p.method==='gcash'?'GCash mobile number':'Account number'}</small><strong>${esc(p.number)}</strong></div><button class="am-secondary" data-copy="${esc(p.number)}">Copy</button><div><small>Reservation number</small><strong>${esc(b.id)}</strong></div><button class="am-secondary" data-copy="${esc(b.id)}">Copy</button></div>${p.instructions?`<p style="white-space:pre-wrap">${esc(p.instructions)}</p>`:''}<form id="am-payment-form"><label class="am-field">Upload your ${p.method==='gcash'?'GCash':'bank'} payment receipt (JPG, PNG or WebP)<input type="file" name="receipt" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" required><small>Upload a clear screenshot or photo of the transfer confirmation. The image is private and only hotel administrators can view it.</small></label><div class="am-error" data-error role="alert"></div><div class="am-form-actions"><button class="am-primary" type="submit">Submit payment receipt</button></div></form>`:b.status==='payment_review'?'<p>Your receipt has been received. The resort will review your payment and availability before confirming the booking.</p>':b.status==='confirmed'?'<p>Your reservation has been confirmed by the resort.</p>':'<p>This reservation is no longer active. Contact the resort for assistance.</p>'}<p class="am-note">Keep your reservation number for your records.</p><div class="am-form-actions"><button class="am-secondary" data-resume>Refresh status</button><button class="am-secondary" data-close>Close</button></div>`,true);
 const f=$('#am-payment-form');
 if(f)f.addEventListener('submit',async e=>{e.preventDefault();const btn=f.querySelector('[type=submit]');btn.disabled=true;try{btn.textContent='Preparing receipt…';const data=await prepareReceipt(f.elements.namedItem('receipt')?.files?.[0]);btn.textContent='Uploading receipt…';await api('payment-receipt',{...lastBooking,data});await resume()}catch(e){error(e);btn.disabled=false;btn.textContent='Submit payment receipt'}});
}
async function resume(){if(!lastBooking)return;show('Your reservation','<p>Loading reservation…</p><div class="am-error" data-error role="alert"></div>',true);const version=viewVersion;try{const b=(await api('booking-status',lastBooking)).booking;if(version===viewVersion)payment(b)}catch(e){error(e)}}
document.addEventListener('click',async e=>{const t=e.target.closest('button,[data-book],[data-cart]');if(!t)return;if(t.matches('[data-book]')){e.preventDefault();beginBooking()}else if(t.matches('[data-dates]')){e.preventDefault();beginBooking()}else if(t.matches('[data-choose]')){e.preventDefault();choose('villa')}else if(t.matches('[data-cart]')){e.preventDefault();renderCart()}else if(t.matches('[data-close]'))close();else if(t.matches('[data-room]')){if(!catalog)catalog=localCatalog();if(modal.hidden){show('Choose your dates','<p>Checking current room price…</p>');const version=viewVersion;await load();if(version===viewVersion)beginBooking(t.dataset.room)}else configure(t.dataset.room)}else if(t.matches('[data-service-kind]'))choose(t.dataset.serviceKind);else if(t.matches('[data-service]')){if(!catalog)catalog=localCatalog();configureService(t.dataset.service,t.dataset.editService)}else if(t.matches('[data-remove-service]')){cart.services=cart.services.filter(x=>serviceKey(x)!==t.dataset.removeService);persist();renderCart()}else if(t.matches('[data-villa-tab]')){const r=catalog?.rooms.find(x=>x.id===t.dataset.villaTab);if(r){villaSelection[r.category||'Villas']=r.id;renderCatalog();$(`[data-villa-tab="${CSS.escape(r.id)}"]`)?.focus({preventScroll:true})}}else if(t.matches('[data-villa-photo]')){const f=t.closest('.am-villa-figure');const image=f.querySelector('img');image.src=t.dataset.villaPhoto;image.alt=resortPhoto(t.dataset.villaPhoto)?'Resort setting':'Villa photograph';const caption=f.querySelector('figcaption');if(caption)caption.hidden=!resortPhoto(t.dataset.villaPhoto)}else if(t.matches('[data-remove]')){cart.rooms=cart.rooms.filter(x=>x.id!==t.dataset.remove);if(!cart.rooms.length)cart.addons=[];persist();renderCart()}else if(t.matches('[data-clear-extras]')){cart.addons=[];persist();renderCart()}else if(t.matches('[data-checkout]'))checkout();else if(t.matches('[data-resume]'))resume();else if(t.matches('[data-copy]')){try{await navigator.clipboard.writeText(t.dataset.copy);t.textContent='Copied'}catch{t.textContent='Select and copy'}}else if(t.matches('[data-photo]')){const el=t.closest('.am-room-card').querySelector('.am-room-image'),im=el.querySelector('img');im.src=t.dataset.photo;im.alt=resortPhoto(t.dataset.photo)?'Resort setting':'Villa photograph';let label=el.querySelector('.am-resort-caption');if(resortPhoto(t.dataset.photo)&&!label){label=document.createElement('small');label.className='am-resort-caption';label.textContent='Resort setting';el.append(label)}if(label)label.hidden=!resortPhoto(t.dataset.photo)}else if(t.matches('[data-video-toggle]')){const v=$('.am-hero-video');if(v.paused){try{await v.play();t.textContent='Pause video';t.setAttribute('aria-label','Pause background video')}catch{}}else{v.pause();t.textContent='Play video';t.setAttribute('aria-label','Play background video')}}else if(t.matches('[aria-label="Toggle menu"]')){const nav=$('.am-mobile-nav');nav.hidden=!nav.hidden;t.setAttribute('aria-expanded',String(!nav.hidden))}});
document.addEventListener('change',e=>{if(e.target.matches('[data-addon]')){const el=e.target,n=Number(el.value);if(!Number.isInteger(n)||n<0||n>99){el.value=0;error(Error('Enter a quantity from 0 to 99.'));return}cart.addons=cart.addons.filter(x=>x.id!==el.dataset.addon);if(n)cart.addons.push({id:el.dataset.addon,qty:n});persist();renderCart()}});
modal.addEventListener('click',e=>{if(e.target===modal)close()});document.addEventListener('keydown',e=>{if(modal.hidden)return;if(e.key==='Escape')close();if(e.key==='Tab'){const targets=$$('button:not(:disabled),a[href],input:not(:disabled),textarea,select',modal).filter(x=>x.getClientRects().length);const first=targets[0],last=targets.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}});

function syncCustomerCare(){
 const c=catalog?.support||{},phone=String(c.phone||''),dial=String(c.dialPhone||phone).replace(/[^+0-9]/g,'');
 const valid=Boolean(phone)&&/^\+?[0-9]{7,15}$/.test(dial);
 const root=document.querySelector('[data-support-details]');
 if(root){
  root.hidden=false;
  const email=$('[data-support-email]',root),hours=$('[data-support-hours]',root),greeting=$('[data-support-greeting]',root);
  const resort=$('[data-support-address]',root),office=$('[data-support-office]',root);
  if(email){
   email.textContent=c.email||'Send a message using the form';
   if(c.email&&/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(c.email))email.href='mailto:'+c.email;
   else email.removeAttribute('href');
  }
  if(hours){hours.textContent=c.hours||'';hours.hidden=!c.hours}
  if(greeting){greeting.textContent=c.greeting||'';greeting.hidden=!c.greeting}
  if(resort){resort.textContent=c.resortAddress||'';resort.closest('[data-support-address-block]').hidden=!c.resortAddress}
  if(office){office.textContent=c.officeAddress||'';office.closest('[data-support-office-block]').hidden=!c.officeAddress}
 }
 $$('[data-support-call]').forEach(link=>{
  link.hidden=!valid;
  if(valid){
   link.href='tel:'+dial;
   link.setAttribute('aria-label','Call AMORAP at '+phone);
   if(link.hasAttribute('data-support-number'))link.textContent=phone;
  }else link.removeAttribute('href');
 });
 // The old large floating CALL button obscured the reservation drawer.
 document.getElementById('am-customer-call')?.remove();
 // Contact details are managed once in Admin, then published across all pages.
 const footer=document.querySelector('footer');
 if(footer){
  let strip=footer.querySelector('.am-site-contact-inline');
  if(!strip){strip=document.createElement('div');strip.className='am-site-contact-inline';footer.append(strip)}
  strip.replaceChildren();
  if(c.resortAddress){const address=document.createElement('span');address.textContent=c.resortAddress;strip.append(address)}
  if(valid){const link=document.createElement('a');link.textContent='Phone: '+phone;link.href='tel:'+dial;strip.append(link)}
  if(c.email){const link=document.createElement('a');link.textContent=c.email;link.href='mailto:'+c.email;strip.append(link)}
  strip.hidden=!strip.children.length;
 }
}

function initLiveChat(){
 // Small, collapsible button; hidden while the booking modal is open.
 const widget=document.createElement('div');widget.className='am-live-chat';
 widget.innerHTML='<button type="button" class="am-chat-toggle" aria-label="Open live chat" aria-expanded="false" title="Chat with AMORAP">💬</button>'+
 '<section class="am-chat-panel" hidden role="region" aria-label="Chat with AMORAP customer care">'+
 '<header class="am-chat-header"><div><strong>AMORAP Live Chat</strong><small>Messages go directly to our team</small></div><button type="button" class="am-chat-close" aria-label="Close chat">×</button></header>'+
 '<div class="am-chat-messages" aria-live="polite"><p class="am-chat-hint">Ask a question. A staff member can reply here.</p></div>'+
 '<div class="am-chat-error" role="alert"></div>'+
 '<form class="am-chat-form"><div class="am-chat-identity"><label>Name (optional)<input name="name" maxlength="100" placeholder="Your name" autocomplete="name"></label><label>Email (optional)<input name="email" type="email" maxlength="200" placeholder="you@example.com" autocomplete="email"></label></div>'+
 '<label class="am-chat-message-label">Message<textarea name="message" required maxlength="1200" rows="2" placeholder="How can we help?"></textarea></label>'+
 '<button class="am-chat-send" type="submit">Send message</button></form>'+
 '<button type="button" class="am-chat-new" hidden>Start a new conversation</button></section>';
 document.body.append(widget);
 const toggle=$('.am-chat-toggle',widget),panel=$('.am-chat-panel',widget),closeButton=$('.am-chat-close',widget);
 const errorBox=$('.am-chat-error',widget),feed=$('.am-chat-messages',widget),form=$('.am-chat-form',widget),newButton=$('.am-chat-new',widget);
 const identity=$('.am-chat-identity',widget);
 let session=null,chat=null,loading=false;
 try{const saved=JSON.parse(localStorage.getItem('amorap-live-chat-v1')||'null');if(saved&&Number.isInteger(saved.id)&&typeof saved.token==='string')session=saved}catch{}
 const setError=message=>{errorBox.textContent=message||'';errorBox.hidden=!message};
 const saveSession=()=>{try{if(session)localStorage.setItem('amorap-live-chat-v1',JSON.stringify(session));else localStorage.removeItem('amorap-live-chat-v1')}catch{}};
 function renderMessages(){
  const messages=chat?.messages||[];
  feed.innerHTML=messages.length?messages.map(m=>'<div class="am-chat-message '+(m.role==='admin'?'is-staff':'is-guest')+'"><small>'+(m.role==='admin'?'AMORAP team':'You')+'</small><p>'+esc(m.text)+'</p></div>').join(''):'<p class="am-chat-hint">Ask a question. A staff member can reply here.</p>';
  feed.scrollTop=feed.scrollHeight;
  identity.hidden=Boolean(session);
  const closed=Boolean(chat&&chat.status==='closed');
  form.hidden=closed;
  newButton.hidden=!closed;
  if(closed)setError('This conversation is closed. You can start a new one.');
  else if(!loading)setError('');
 }
 async function poll(){
  if(!session||loading||panel.hidden||document.visibilityState==='hidden')return;
  loading=true;
  try{const data=await api('chat/poll',session);chat=data.chat;renderMessages()}
  catch(e){
   if(/not found/i.test(e.message)){session=null;chat=null;saveSession();renderMessages()}
   else setError('Chat connection interrupted. Your messages remain saved; retry shortly.');
  }finally{loading=false}
 }
 toggle.addEventListener('click',()=>{
  panel.hidden=!panel.hidden;
  toggle.setAttribute('aria-expanded',String(!panel.hidden));
  toggle.setAttribute('aria-label',panel.hidden?'Open live chat':'Hide live chat');
  if(!panel.hidden){renderMessages();poll();form.querySelector('[name=message]')?.focus({preventScroll:true})}
 });
 closeButton.addEventListener('click',()=>{panel.hidden=true;toggle.setAttribute('aria-expanded','false');toggle.setAttribute('aria-label','Open live chat');toggle.focus()});
 newButton.addEventListener('click',()=>{session=null;chat=null;saveSession();renderMessages();form.querySelector('[name=message]').focus()});
 form.addEventListener('submit',async e=>{
  e.preventDefault();if(loading)return;
  const input=form.elements.namedItem('message'),text=input.value.trim();if(!text)return;
  const button=form.querySelector('[type=submit]');
  loading=true;button.disabled=true;setError('');
  try{
   const data=session?
    await api('chat/send',{...session,message:text}):
    await api('chat/start',{name:form.elements.namedItem('name').value,email:form.elements.namedItem('email').value,message:text});
   if(!session){session={id:data.chat.id,token:data.token};saveSession()}
   chat=data.chat;input.value='';renderMessages();
  }catch(err){setError(err.message)}
  finally{loading=false;button.disabled=false}
 });
 window.setInterval(poll,8000);
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')poll()});
}
const cf=$('#contact-form');if(cf){const topic=new URLSearchParams(location.search).get('topic');const subjects={dining:'Dining inquiry',event:'Event inquiry',careers:'Careers inquiry'};if(subjects[topic])cf.elements.namedItem('message').value=subjects[topic]+':\n';}if(cf)cf.addEventListener('submit',async e=>{e.preventDefault();const btn=cf.querySelector('button'),res=$('#contact-result');btn.disabled=true;try{await api('contact',Object.fromEntries(new FormData(cf)));res.textContent='Your message has been sent to the resort dashboard.';cf.reset()}catch(e){res.textContent=e.message}finally{btn.disabled=false}});
persist();initLiveChat();load().then(syncCustomerCare).catch(()=>{});if($('#villa-catalog')||$('#event-catalog')||$('#dining-catalog')){load().then(renderAll);}if(document.body.dataset.openBooking)beginBooking();else if(document.body.dataset.openCheckout)renderCart();
const heroVideo=$('.am-hero-video');if(heroVideo&&matchMedia('(prefers-reduced-motion: reduce)').matches){heroVideo.autoplay=false;heroVideo.pause();const b=$('[data-video-toggle]');b.textContent='Play video';b.setAttribute('aria-label','Play background video');}

// The site header changes from transparent over the photographic hero to cream on scroll.
const siteHeader=$('.am-site-header');
if(siteHeader){
  const hero=$('[data-am-hero]');
  const syncHeader=()=>siteHeader.classList.toggle('is-scrolled',!hero||hero.getBoundingClientRect().bottom<=siteHeader.offsetHeight);
  window.addEventListener('resize',syncHeader,{passive:true});
  syncHeader();window.addEventListener('scroll',syncHeader,{passive:true});window.addEventListener('pageshow',syncHeader);
  const menu=$('.am-mobile-nav',siteHeader),toggle=$('.am-menu-toggle',siteHeader);
  const closeMenu=()=>{menu.hidden=true;toggle.setAttribute('aria-expanded','false');};
  const desktop=matchMedia('(min-width:1024px)');
  desktop.addEventListener('change',e=>{if(e.matches)closeMenu()});
  menu.addEventListener('click',e=>{if(e.target.closest('a'))closeMenu()});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!menu.hidden){closeMenu();toggle.focus({preventScroll:true});}});
}
