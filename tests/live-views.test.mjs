import test from 'node:test';
import assert from 'node:assert/strict';
import { mountWatches,unmountWatches } from '../src/live-watches.js';
import { mountDiscovery,unmountDiscovery } from '../src/live-discovery.js';
import {sadAvatarSvg} from '../src/art.js';
function host(){const listeners={};return {isConnected:true,dataset:{},innerHTML:'',addEventListener:(name,fn)=>{listeners[name]=fn;},querySelector:()=>null,listeners};}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const response=value=>({ok:true,status:200,json:async()=>structuredClone(value)});
test('saved price lists restore, but input, unsaved results and diagnostics do not',async()=>{
 const previous=globalThis.fetch;const w={id:'watch-1',name:'My waterproof boots',query:'Boots',sites:[],status:'active',city:'Copenhagen',cadenceHours:0,lastOffers:[{title:'UNSAVED_GHOST'}],diagnostics:[{reason:'OLD_DIAGNOSTIC'}],savedOptions:[{id:'opt-1',title:'Waterproof boots',priceMinor:12999,currency:'EUR',store:'Shop',url:'https://shop.example/boots',availabilityEvidence:'In stock',images:['https://merchant.example/ORIGINAL_MUST_NOT_RENDER.jpg']}]};
 globalThis.fetch=async()=>response({items:[w]});
 try{const h=host();mountWatches(h);await tick();assert.match(h.innerHTML,/My waterproof boots/);assert.match(h.innerHTML,/Waterproof boots/);assert.match(h.innerHTML,/Rerun prices manually/);assert.match(h.innerHTML,/Preview in your space/);assert.match(h.innerHTML,/Generate 360° video/);assert.doesNotMatch(h.innerHTML,/ORIGINAL_MUST_NOT_RENDER|Create photo rotation/);assert.match(h.innerHTML,/Websites \(optional/);assert.doesNotMatch(h.innerHTML,/UNSAVED_GHOST|OLD_DIAGNOSTIC|temporary-watch-results/);assert.match(h.innerHTML,/name="query" value=""/);unmountWatches();const h2=host();mountWatches(h2);await tick();assert.match(h2.innerHTML,/name="query" value=""/);
 }finally{unmountWatches();globalThis.fetch=previous;}
});
test('Discover loads saved trips collapsed and never restores unsaved research history',async()=>{
 const previous=globalThis.fetch,calls=[];const event={id:'event-1',title:'Science night',when:'Nov-Dec 2099',where:'Copenhagen',price:'Free',sources:[]};
 globalThis.fetch=async url=>{calls.push(url);return response({items:[{id:'trip-1',title:'My science trip',items:[event],notice:'Saved plan',teasers:{}}]});};
 try{const h=host();mountDiscovery(h);await tick();assert.match(h.innerHTML,/My science trip/);assert.match(h.innerHTML,/saved-trip-details" hidden/);assert.doesNotMatch(h.innerHTML,/Saved research outputs|class="event-card"/);assert.deepEqual(calls,['/api/v1/itineraries']);await h.listeners.click({target:{closest:()=>({dataset:{discovery:'toggle-trip',id:'trip-1'}})}});assert.doesNotMatch(h.innerHTML,/saved-trip-details" hidden/);assert.match(h.innerHTML,/aria-expanded="true"/);
 }finally{unmountDiscovery();globalThis.fetch=previous;}
});
test('missing-product mascot has the sad mouth and no animation hooks',()=>{const svg=sadAvatarSvg();assert.match(svg,/M91 118 Q100 108 109 118/);assert.doesNotMatch(svg,/class="av-|class="agent-avatar/);});
