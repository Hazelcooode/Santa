import { retryProductImage } from './product-images.js';
import { scopeFields, readScope } from './search-scope.js';
import { request } from './api-client.js';
import { safeText as esc } from './model.js';
import { ico, cash, hero, empty, source } from './ui.js';
let host, items=[], settings={city:'',country:'',currency:'EUR',domains:[]},busy=false,message='',result=null,editing=null,strategy='multi',loadId=0;
let poll,messageError=false,failureCode='',category='All items';
const expandedStores=new Set();
const format=n=>cash(n,settings.currency);
const button=(text,action,extra='')=>`<button type="button" class="button secondary" data-live="${action}" ${busy?'disabled':''} ${extra}>${text}</button>`;
const attrs=values=>Object.entries(values||{}).map(([k,v])=>`${k}=${v}`).join('\n');
const date=value=>new Date(value).toLocaleString();
const aisle=i=>i.attributes?.category||'Uncategorised';
function shopKey(offer){
 try{const url=new URL(offer.url);if(['http:','https:'].includes(url.protocol))return url.hostname.toLowerCase().replace(/^www\./,'');}catch{}
 return offer.store||'Unknown shop';
}
function comparisons(){
 const open=items.filter(i=>!i.bought),map=new Map();
 for(const raw of settings.domains||[]){const name=raw.toLowerCase().replace(/^www\./,'');map.set(name,{name,quotes:new Map()});}
 for(const item of open){
  for(const offer of item.offers||[]){
   if(offer.stale||offer.currency!==settings.currency||!Number.isFinite(offer.priceMinor)||offer.priceMinor<0)continue;
   const name=shopKey(offer),store=map.get(name)||{name,quotes:new Map()},previous=store.quotes.get(item.id);
   if(!previous||offer.priceMinor<previous.priceMinor)store.quotes.set(item.id,offer);
   map.set(name,store);
  }
 }
 return [...map.values()].map(store=>{
  const lines=open.map(item=>({item,offer:store.quotes.get(item.id)||null}));
  const count=store.quotes.size,total=lines.reduce((sum,line)=>sum+(line.offer?Math.round(line.offer.priceMinor*line.item.qty):0),0);
  return {name:store.name,lines,count,total,complete:count===open.length&&open.length>0};
 }).sort((a,b)=>Number(b.complete)-Number(a.complete)||Number(b.count>0)-Number(a.count>0)||a.total-b.total);
}
function storeBasket(store,index,max){
 return `<details class="store-comparison ${store.complete&&index===0?'best':''}" data-store-basket="${esc(store.name)}" ${expandedStores.has(store.name)?'open':''}>
 <summary><div class="store-basket-heading"><span>${esc(store.name)}${store.complete&&index===0?' <small class="ui-tag sage">Lowest complete basket</small>':''}</span><strong>${store.count?format(store.total):'No quotes'}</strong></div><div class="comparison-track"><span style="width:${store.count?Math.max(3,Math.round(store.total/max*100)):0}%"></span></div><span class="store-basket-caption">${store.count}/${store.lines.length} items quoted · ${store.complete?'complete known subtotal':'partial basket'} <span>View items</span></span></summary>
 <ul class="store-basket-items">${store.lines.map(({item,offer})=>`<li class="store-basket-item ${offer?'':'missing'}"><span>${offer?`<strong>${esc(item.name)}</strong>`:`<s>${esc(item.name)}</s>`}<small>${item.qty} ${!offer?'units':offer.priceBasis==='item'?'items':'packages'}${item.brand?' · '+esc(item.brand):''}</small></span>${offer?`<span class="store-item-price"><strong>${format(Math.round(offer.priceMinor*item.qty))}</strong><small>${format(offer.priceMinor)} each × ${item.qty}</small></span>${source(offer.url,'View item','store-item-link')}`:'<span class="store-item-missing">No current quote</span>'}</li>`).join('')}</ul>
 <p class="ui-note store-basket-note">Lowest saved quote for each item at this shop, multiplied by quantity. Missing quotes are not proof of stock availability. Delivery and travel excluded.</p></details>`;
}

function render(){
 if(!host?.isConnected)return;
 const item=editing?items.find(i=>i.id===editing):null,open=items.filter(i=>!i.bought),known=open.filter(i=>i.priceStatus==='fresh'&&i.quote),total=known.reduce((s,i)=>s+Math.round(i.quote.priceMinor*i.qty),0),stores=comparisons();

 const categories=['All items',...new Set(items.map(aisle))];if(!categories.includes(category))category='All items';
 const selected=new Map((result?.strategy===strategy?result.plan||[]:[]).flatMap(p=>p.lines.map(l=>[l.item.id,{...l,store:p.store}])));
 const planned=result?.strategy===strategy&&Array.isArray(result?.plan);
 const visible=items.filter(i=>category==='All items'||aisle(i)===category).map(i=>{
  if(!planned||i.bought)return i;
  const line=selected.get(i.id);if(!line)return {...i,quote:null};
  const minor=Math.round(line.price*100),domain=line.store.id;
  const quote=(i.offers||[]).find(o=>o.priceMinor===minor&&!o.stale&&(o.store===line.store.name||(()=>{try{return new URL(o.url).hostname.replace(/^www\./,'')===domain;}catch{return false;}})()));
  return {...i,quote:quote||null};
 });
 const comparisonMax=Math.max(...stores.map(s=>s.total),1);
 host.innerHTML=`<section class="sola-screen groceries-screen">${hero('Your procurement companion','Your list. Your shops.<br><em>Current prices.</em>','Full package prices, sourced from the shops you choose.')}
 <div class="ui-panel store-strip">${ico('store')}<strong>Target stores:</strong>${settings.domains.length?settings.domains.map(d=>`<span class="store-chip"><i class="status-dot"></i>${esc(d)}</span>`).join(''):`<span class="ui-note">${settings.shopMode==='nearby'?'Discover nearby retailers when checking prices':'Choose your shops below'}</span>`}<div class="ui-actions"><span class="ui-note">${esc(settings.city||'Location not set')}</span>${button(ico('tune')+' Search settings','settings')}</div></div>
 <details class="ui-panel store-settings" id="shop-settings" ${!settings.city?'open':''}><summary>Search location &amp; grocery chains</summary><form data-form="settings" class="ui-form">
 <label class="field"><span>City</span><input name="city" value="${esc(settings.city)}" maxlength="100" placeholder="Choose your city" required></label><label class="field"><span>Your country code</span><input name="country" value="${esc(settings.country)}" minlength="2" maxlength="2" placeholder="FI" required></label><label class="field"><span>Currency</span><input name="currency" value="${esc(settings.currency)}" minlength="3" maxlength="3" required></label><label class="field"><span>Which shops?</span><select name="shopMode"><option value="selected" ${settings.shopMode!=='nearby'?'selected':''}>My selected websites</option><option value="nearby" ${settings.shopMode==='nearby'?'selected':''}>Discover shops in my city</option></select></label>${scopeFields(settings)}<label class="field wide"><span>Shop websites (comma-separated domains; required for selected shops)</span><input name="domains" value="${esc(settings.domains.join(', '))}" placeholder="s-kaupat.fi, k-ruoka.fi"></label><button class="button dark">Save search settings</button></form><p class="ui-note">Nearby discovery is opt-in and checks up to five retailers. Branch stock, delivery fees and distance may be unknown.</p></details>
 <p role="${messageError?'alert':'status'}" aria-live="polite" class="live-status ${messageError?'error':''}">${esc(message)}</p>
 <div class="grocery-grid"><div><div class="ui-panel queue-bar"><span class="status-dot"></span><strong class="queue-count">${open.length} items<br>queued</strong><p class="queue-meta">${known.length} with fresh quotes<br>known subtotal <strong>${format(total)}</strong></p>${button(ico('refresh')+' Reload saved list','reload')}<button type="button" class="button dark" data-live="refresh" ${busy?'disabled':''}>${ico('refresh')} ${busy?'Updating prices...':'Update prices'}</button></div>
 <div class="filter-row">${categories.map(c=>`<button class="filter-pill ${category===c?'active':''}" data-live="filter" data-category="${esc(c)}">${esc(c)} (${c==='All items'?items.length:items.filter(i=>aisle(i)===c).length})</button>`).join('')}<span class="filter-note">Your saved categories</span></div>
 <div class="grocery-items">${visible.map(i=>`<article class="grocery-row ${i.bought?'is-bought':''}"><button class="item-toggle" data-live="bought" data-id="${esc(i.id)}" aria-label="${i.bought?'Mark not bought':'Mark bought'}: ${esc(i.name)}" aria-pressed="${!!i.bought}" ${busy?'disabled':''}>${i.bought?ico('check'):''}</button><div class="item-thumbnail">${i.quote?.image?`<img src="${esc(i.quote.image)}" alt="${esc(i.name)}" loading="lazy">`:ico('bag')}</div><div class="item-copy"><div class="item-name-row"><h3>${esc(i.name)}</h3><span class="qty-badge">Qty: ${i.qty} ${!i.quote?'units':i.quote.priceBasis==='item'?(i.qty===1?'item':'items'):(i.qty===1?'package':'packages')}</span></div><p><span class="retailer-name">${esc(i.quote?.store||i.brand||'Waiting for a matching quote')}</span> &middot; ${esc(aisle(i))}</p>${i.details?`<p>${esc(i.details)}</p>`:''}<p>${i.quote?'Checked '+esc(date(i.quote.fetchedAt)):'Not priced yet'}${i.prio===1?' &middot; Urgent':''}</p></div><div class="item-price">${i.quote?`<strong>${format(Math.round(i.quote.priceMinor*i.qty))}</strong><small>${format(i.quote.priceMinor)} per ${i.quote.priceBasis==='item'?'item':'package'} &times; ${i.qty} &middot; ${esc(i.priceStatus)}</small><span class="ui-tag sage">${i.offers?.length>1?'Lowest known quote':'Sourced quote'}</span>`:'<span class="ui-tag">Price unknown</span>'}</div><div class="row-tools"><button class="icon-button" data-live="edit" data-id="${esc(i.id)}" aria-label="Edit ${esc(i.name)}">${ico('edit')}</button><button class="icon-button" data-live="delete" data-id="${esc(i.id)}" aria-label="Remove ${esc(i.name)}">${ico('trash')}</button></div>${i.offers?.length?`<details class="row-sources"><summary>${i.offers.length} saved source${i.offers.length===1?'':'s'}</summary>${i.offers.map(o=>`<p>${source(o.url,o.product+' - '+o.store)} &mdash; ${format(o.priceMinor)}<br>${esc(o.evidence||'Source claim; verify before purchasing.')}</p>`).join('')}</details>`:''}</article>`).join('')||empty('A little room in your basket','Add your first item and choose the shops you want Sola to compare.','bag')}</div>
 <section class="ui-panel basket-total-summary"><div>${ico('bag')}<h2>Known basket</h2><span>${known.length}/${open.length} items with fresh quotes</span></div><strong>${format(total)}</strong><p>Lowest known item prices × quantity. ${open.length-known.length} without a fresh quote; delivery and travel excluded.</p></section>
 <section class="ui-panel basket-differential"><div class="ui-section-title">${ico('chart')}<h2>Store basket price differential</h2><small>Sourced quotations</small></div>${stores.length?stores.map((store,index)=>storeBasket(store,index,comparisonMax)).join(''):'<p class="ui-note">Update prices to compare your selected shops. We show totals only for sourced quotes.</p>'}<div class="ui-form" style="margin-top:22px"><label class="field"><span>Shopping strategy</span><select id="live-strategy">${[['multi','Lowest known item prices'],['single','One store'],['mall','Same shopping centre (if known)'],['nearest','Nearest (if distance known)']].map(([v,t])=>`<option value="${v}" ${strategy===v?'selected':''}>${t}</option>`).join('')}</select></label>${button('Compare current list','compare')}</div></section>
 ${result?.plan?`<section class="ui-panel selected-basket"><div class="ui-section-title">${ico('bag')}<h2>${strategy==='single'?'One-store basket':strategy==='multi'?'Lowest known item prices':'Selected basket strategy'}</h2></div>${result.plan.map(p=>`<div class="basket-store-group"><h3>${esc(p.store.name)} <strong>${format(p.total*100)}</strong></h3>${p.lines.map(l=>`<p>${esc(l.item.name)} <span>${l.qty} &times; ${format(Math.round(l.price*100))} = <strong>${format(Math.round(l.price*100*l.qty))}</strong></span></p>`).join('')}</div>`).join('')||'<p>No saved quotes available for this strategy.</p>'}<p class="ui-note">${esc(result.note||'')} ${(result.unpriced||[]).length} unpriced; delivery/travel excluded.</p><p class="basket-grand-total">Known total <strong>${format(result.totalMinor||0)}</strong></p></section>`:''}${result?`<details class="ui-panel audit-panel" open><summary>${ico('tune')} Price lookup details</summary><p class="ui-note">${esc(result.notice||result.note||'')}</p>${(result.storeCoverage||[]).map(c=>`<p class="audit-row">${esc(c.domains.join(', ')||'Open web')} &middot; ${esc(c.status)} &middot; ${c.pages} pages ${esc(c.reason||'')}</p>`).join('')}${(result.diagnostics||[]).map(d=>`<div class="audit-row">${esc(d.item||'Item')}: ${esc(d.reason)} ${d.url?source(d.url,'Inspected page'):''}</div>`).join('')}${result.proposalId?source('/api/v1/shopping/proposals/'+encodeURIComponent(result.proposalId)+'/print','Print this sourced plan','button secondary'):''}</details>`:''}</div>
 <aside><section class="ui-panel grocery-add"><div class="ui-section-title"><span class="status-dot"></span><h2>${item?'Edit your item':'Add an item'}</h2><small>Saved list</small></div><form data-form="item" class="ui-form"><label class="field"><span>Item / Type *</span><input name="name" value="${esc(item?.name||'')}" placeholder="e.g. Oat milk, avocados, yoghurt" maxlength="80" required></label><label class="field"><span>Brand <span class="muted">(optional)</span></span><input name="brand" value="${esc(item?.brand||'')}" placeholder="e.g. Oatly, Rainbow, Valio" maxlength="100"></label><label class="field"><span>Quantity (items / packages)</span><input name="qty" type="number" min="0.01" max="10000" step="0.01" value="${item?.qty||1}" required></label><div class="ui-actions">${[1,2,4].map(n=>button(n+' unit'+(n===1?'':'s'),'quantity',`data-quantity="${n}"`)).join('')}</div><label class="field"><span>Urgency / Priority</span><select name="prio">${[[2,'Routine'],[1,'Urgent'],[3,'Flexible']].map(([n,t])=>`<option value="${n}" ${(item?.prio||2)===n?'selected':''}>${t}</option>`).join('')}</select></label><label class="field"><span>Category / aisle <span class="muted">(optional)</span></span><input name="aisle" value="${esc(item?.attributes?.category||'')}" placeholder="Produce, dairy, pantry..." maxlength="60"></label><label class="field"><span>Product details <span class="muted">(variant, sizing)</span></span><textarea name="details" maxlength="400" placeholder="Flavour, exact package size, dietary needs...">${esc(item?.details||'')}</textarea></label><details><summary class="ui-note">Additional product attributes</summary><label class="field"><span>One key=value per line</span><textarea name="attributes" rows="3" placeholder="flavour=hot honey">${esc(attrs(Object.fromEntries(Object.entries(item?.attributes||{}).filter(([key])=>key!=='category'))))}</textarea></label></details><button class="button dark" ${busy?'disabled':''}>${ico(item?'save':'bag')} ${item?'Save changes':'Add item'}</button>${item?button('Cancel edit','cancel'):''}</form></section><section class="basket-insight"><div class="ui-section-title">${ico('spark')}<h3>Sola basket insights</h3></div><p>${known.length?`${open.length-known.length} item${open.length-known.length===1?'':'s'} still need a fresh quote. Compare complete baskets before choosing a shop.`:'Choose exact brands and package sizes for more useful comparisons. Your list is saved to your account.'}</p><p class="ui-note">Full package prices only. No stock, travel or delivery costs are invented.</p></section></aside></div>
 <p class="screen-disclaimer">Quotes are page claims, not checkout guarantees. No purchase was made. Other external actions remain clearly labeled simulations.</p></section>`;
}
function publish() { window.dispatchEvent(new CustomEvent('taimi-shopping-updated',{detail:items})); }
async function load() {
  const id = ++loadId;
  const [list, config] = await Promise.all([request('/shopping/items'),request('/shopping/settings')]);
  if (id!==loadId) return;
  items=list.items; settings=config; publish(); render();
}
async function run(fn) {
  if (busy) return; busy=true; message='';messageError=false;failureCode=''; render();
  try { await fn(); } catch(e) { message=e.message;messageError=true;failureCode=e.code; } finally { busy=false; render();if(messageError){if(failureCode==='SEARCH_SETTINGS_REQUIRED'||failureCode==='INVALID_COUNTRY')host?.querySelector('#shop-settings')?.setAttribute('open','');host?.querySelector('.live-status')?.scrollIntoView({behavior:'smooth',block:'center'});} }
}
function parseAttributes(text) {
  const out={}; for (const line of text.split('\n').filter(l=>l.trim())) { const at=line.indexOf('='); if(at<1) throw Error('Use key=value for every attribute line.'); const k=line.slice(0,at).trim(),v=line.slice(at+1).trim(); if(!v||k.length>60||v.length>200) throw Error('Each attribute needs a key (up to 60 characters) and value (up to 200).'); out[k]=v; } if(Object.keys(out).length>20) throw Error('Use at most 20 attributes.'); return out;
}
function bind(target) {
  target.addEventListener('toggle',event=>{const key=event.target.dataset?.storeBasket;if(key&&event.target.isConnected)event.target.open?expandedStores.add(key):expandedStores.delete(key);},true);
  target.addEventListener('submit',event=>{
    const form=event.target.closest('[data-form]'); if(!form)return; event.preventDefault();
    const data=new FormData(form);
    let body; try { body=form.dataset.form==='settings'?{...readScope(data),shopMode:data.get('shopMode'),city:data.get('city'),country:data.get('country').toUpperCase(),currency:data.get('currency').toUpperCase(),domains:data.get('domains').split(',').map(s=>s.trim()).filter(Boolean)}:{name:data.get('name'),brand:data.get('brand'),details:data.get('details'),qty:Number(data.get('qty')),prio:Number(data.get('prio')),attributes:{...parseAttributes(data.get('attributes')||''),...(data.get('aisle')?.trim()?{category:data.get('aisle').trim()}:{})}}; } catch(e){message=e.message;const status=target.querySelector('.live-status');if(status)status.textContent=message;return;}
    // Preserve form edits on failed requests rather than replacing the form.
    if(busy)return; busy=true;messageError=false; const submit=form.querySelector('button[type="submit"],button:not([type])');if(submit)submit.disabled=true;
    (async()=>{let succeeded=false;try {
      if(form.dataset.form==='settings'){await request('/shopping/settings',{method:'PUT',body});result=null;}
      else {if(editing){body.expectedVersion=items.find(i=>i.id===editing).version;await request('/shopping/items/'+encodeURIComponent(editing),{method:'PATCH',body});}else await request('/shopping/items',{method:'POST',body});editing=null;result=null;}
      message='Saved to your account. New and changed products remain price unknown until you choose Update prices.';await load();succeeded=true;

    }catch(e){message=e.message;messageError=true;const status=target.querySelector('.live-status');if(status){status.textContent=message;status.classList.add('error');status.setAttribute('role','alert');status.scrollIntoView({behavior:'smooth',block:'center'});}}finally{busy=false;if(succeeded)render();else if(submit)submit.disabled=false;}})();
  });
  target.addEventListener('change',event=>{if(event.target.id==='live-strategy'){strategy=event.target.value;run(async()=>{result=await request('/shopping/deals',{method:'POST',body:{strategy,cachedOnly:true}});message=result.notice;render();});}});
  target.addEventListener('click',event=>{
    const el=event.target.closest('[data-live]');if(!el)return;
    const a=el.dataset.live,id=el.dataset.id,item=items.find(i=>i.id===id);
    if(a==='settings'){const details=target.querySelector('#shop-settings');details.open=!details.open;details.scrollIntoView({behavior:'smooth',block:'start'});return;}
    if(a==='filter'){category=el.dataset.category;render();return;}
    if(a==='quantity'){target.querySelector('[name=qty]').value=el.dataset.quantity;return;}
    if(a==='edit'){editing=id;render();target.querySelector('[name="name"]')?.focus();return;}
    if(a==='cancel'){editing=null;render();return;}
    run(async()=>{
      if(a==='reload')await load();
      if(a==='refresh'){result=await request('/shopping/prices/refresh',{method:'POST',body:{force:true,strategy}});message=result.notice;await load();}
      if(a==='compare'){result=await request('/shopping/deals',{method:'POST',body:{strategy,cachedOnly:true}});message=result.notice||'Compared current account items.';await load();}
      if(a==='delete'){await request('/shopping/items/'+encodeURIComponent(id),{method:'DELETE'});result=null;await load();}
      if(a==='bought'){await request('/shopping/items/'+encodeURIComponent(id),{method:'PATCH',body:{bought:!item.bought,expectedVersion:item.version}});result=null;await load();}
    });
  });
}
export function mountShopping(target) {
  clearTimeout(poll);host=target;if(!host)return;
  if(!target.dataset.liveBound){target.dataset.liveBound='true';bind(target);
    target.addEventListener('error',event=>{if(event.target.matches?.('.item-thumbnail img'))retryProductImage(event.target,()=>{event.target.parentElement.innerHTML=ico('bag');});},true);
  }
  render();load().catch(e=>{message=e.message;render();});
}
window.TaimiShopping={mount:mountShopping};
if(window.FIGMENT_USE_BACKEND && location.hash==='#/shopping') mountShopping(document.querySelector('#shop-list'));
