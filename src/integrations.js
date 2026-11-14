import { request } from './api-client.js';
import { safeText as esc } from './model.js';
const target=document.querySelector('#integration-status'),status=document.querySelector('#probe-status');
try{
  const data=await request('/integrations');
  target.innerHTML=`<p>Environment: <strong>${esc(data.environment)}</strong> · data mode: <strong>${esc(data.dataMode)}</strong> · database: ${esc(data.database)}</p><p>Automatic price lookup: ${data.automaticPriceLookup?'enabled':'off'} · scheduler: ${data.scheduler?'enabled':'off'}</p><p class="small-text muted">${esc(data.notice)}</p>${Object.entries(data.providers).map(([name,p])=>`<div class="privacy-row"><span><strong>${esc(name)}</strong> — ${p.configured?'credential configured':'not configured'} ${p.model?esc(p.model):''}</span><button class="button secondary" data-provider="${name}">Check connection</button></div>`).join('')}`;
  document.querySelector('#simulation-list').textContent=data.simulations.join(', ')+'.';
}catch(e){target.textContent=e.message;}
target.addEventListener('click',async event=>{
  const b=event.target.closest('[data-provider]');if(!b)return;b.disabled=true;status.textContent='Checking '+b.dataset.provider+'…';
  try{const result=await request('/integrations/'+b.dataset.provider+'/check',{method:'POST'});status.textContent=result.ok?`${result.provider}: connection verified${result.costUsd!==undefined?' · reported/estimated cost $'+result.costUsd:''}.`:`${result.provider}: unavailable. ${result.reason||result.notice||'Check key, model and quota.'}`;}catch(e){status.textContent=e.message;}finally{b.disabled=false;}
});
