import test from 'node:test';
import assert from 'node:assert/strict';
import {createPreviewApi} from '../src/preview-api.js';
const storage=()=>{const rows=new Map();return {getItem:k=>rows.get(k)||null,setItem:(k,v)=>rows.set(k,v),rows};};
test('preview saves named lists but never persists unsaved prompts or event outputs',async()=>{
 const s=storage(),api=createPreviewApi(s);
 const research=await api('/price-watch-research',{method:'POST',body:{query:'laptop',details:'TEMP_UNSAVED_MARKER',city:'Demo',country:'FI',sites:[]}});
 assert.ok(research.offers.length>0);assert.ok(![...s.rows.values()].join('').includes('TEMP_UNSAVED_MARKER'));
 await assert.rejects(api('/price-watch-lists',{method:'POST',body:{name:'',saveToken:research.saveToken,count:5}}),/name/);
 const saved=await api('/price-watch-lists',{method:'POST',body:{name:'My laptop list',saveToken:research.saveToken,count:5,cadenceHours:6}});
 assert.equal(saved.savedOptions.length,4);assert.equal(saved.details,'TEMP_UNSAVED_MARKER');
 const search=await api('/explore',{method:'POST',body:{query:'TEMP_EVENT_PROMPT',kind:'events'}});
 assert.deepEqual((await api('/research-searches')).items,[]);assert.ok(![...s.rows.values()].join('').includes('TEMP_EVENT_PROMPT'));
 await api('/itineraries',{method:'POST',body:{title:'Preview weekend',choices:[{searchId:search.searchId,resultId:search.results[0].id}]}});
 const restored=createPreviewApi(s);assert.equal((await restored('/itineraries')).items[0].title,'Preview weekend');assert.ok((await restored('/price-watches')).items.some(w=>w.name==='My laptop list'));
});
test('static strategies display a basket, and custom items remain unknown',async()=>{const api=createPreviewApi(storage());const multi=await api('/shopping/deals',{method:'POST',body:{strategy:'multi'}});assert.ok(multi.plan.length>0);assert.equal(multi.totalMinor,1186);const item=await api('/shopping/items',{method:'POST',body:{name:'New item',qty:6,attributes:{}}});assert.equal(item.quote,null);const single=await api('/shopping/deals',{method:'POST',body:{strategy:'single'}});assert.equal(single.plan.length,1);assert.equal(single.unpriced.length,1);await assert.rejects(api('/itineraries/demo/media',{method:'POST'}),/Python backend/);});

test('offline preview never persists room photos or fakes generated outputs',async()=>{
 const s=storage(),api=createPreviewApi(s);
 await assert.rejects(api('/visual-previews',{method:'POST',body:{kind:'space',imageData:'PRIVATE_ROOM_MARKER'}}),/Python backend/);
 assert.ok(![...s.rows.values()].join('').includes('PRIVATE_ROOM_MARKER'));
});
