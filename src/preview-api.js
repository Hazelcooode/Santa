// Explicit offline website preview. Never used by account-connected pages.
const KEY='sola-interface-preview-v1';
const initial=()=>{
 const stamp=new Date().toISOString();
 const offer=(id,title,minor,store)=>({id,title,product:title,priceMinor:minor,currency:'EUR',store,url:'https://example.com/',checkedAt:stamp,fetchedAt:stamp,availabilityEvidence:'Fictional demo availability',images:[],stale:false,evidence:'Fictional package price for the offline UI preview.'});
 const items=[['milk','Oat milk 1 L','Dairy',2,169],['bread','Rye bread','Bakery',1,249],['coffee','Coffee beans 500 g','Pantry',1,599]].map(([id,name,category,qty,price])=>{const a=offer(id,name,price,'Demo Market'),b=offer(id+'b',name,price+20,'Sample Foods');return {id,name,qty,brand:'',details:'',attributes:{category},prio:2,bought:null,version:1,priceStatus:'fresh',quote:a,offers:[a,b]};});
 const options=[offer('option-a','Demo gaming laptop - RTX 5060, 16 GB RAM',89900,'Demo Electronics'),offer('option-b','Sample notebook - 16 GB RAM, 512 GB SSD',94900,'Sample Tech'),offer('option-c','Demo performance laptop',101900,'Demo Electronics'),offer('option-d','Sample OLED notebook',129900,'Sample Tech')];
 const events=['Nordic comedy night','Late night comedy roster','An intimate stand-up evening','Jazz & winter market','Winter architecture walk','Vinyl listening afternoon'].map((title,i)=>({id:'event-'+i,title,when:'18 December 2026 - see demo schedule',startDate:'2026-12-18',endDate:'2026-12-18',where:'Sample venue, Copenhagen',price:['140 DKK','120 DKK','160 DKK','Free admission','175 DKK','220 DKK'][i],summary:'Fictional event for exploring the interface. Live event details require the backend and Exa.',eventPageType:'single_event',tags:[['Comedy','Intimate club','Stand-up','Outdoor music','Walking tour','Vinyl listening'][i]],images:[],sources:[{title:'Fictional event source',url:'https://example.com/'}]}));
 return {settings:{city:'Helsinki (demo)',country:'FI',currency:'EUR',domains:['demo-market.example','sample-foods.example'],shopMode:'selected',searchScope:'country',searchCountries:[]},items,watches:[{id:'watch-demo',query:'Gaming laptop',details:'RTX 5060, 16 GB RAM, 512 GB SSD',city:'Helsinki (demo)',country:'FI',currency:'EUR',mode:'explore',sites:[],status:'active',cadenceHours:0,targetMinor:100000,version:1,name:'Demo laptop shortlist',savedOptions:options,saveCount:4,lastCheckedAt:stamp,checkState:'ready',checkNotice:'Fictional preview offers. Live prices require the backend and Exa.',diagnostics:[]}],searches:[{searchId:'research-demo',query:'Copenhagen - a sample weekend',kind:'events',mode:'demo',createdAt:stamp,results:events}],trips:[]};
};
export function createPreviewApi(storage){
 let data;try{data=JSON.parse(storage.getItem(KEY));}catch{}if(!data||!Array.isArray(data.items))data=initial();
 const drafts=new Map();data.searches=[];for(const w of data.watches){delete w.lastOffers;delete w.diagnostics;}
 const save=()=>{try{storage.setItem(KEY,JSON.stringify(data));}catch{}};
 const id=prefix=>prefix+'-'+Math.random().toString(36).slice(2,10);
 const error=message=>{throw Error(message);};
 return async function previewRequest(path,{method='GET',body={}}={}){
  let result;
  if(path==='/price-watch-research'){
    const offers=/laptop|notebook/i.test(body.query)?initial().watches[0].savedOptions:[];
    result={mode:'demo',offers,diagnostics:[],notice:'Fictional preview results only.',saveToken:JSON.stringify({spec:body,offers})};
  }
  else if(path==='/price-watch-lists'){
    if(!body.name?.trim())error('Enter a name for this saved list.');
    const proof=JSON.parse(body.saveToken),w={...proof.spec,id:id('watch'),name:body.name.trim(),savedOptions:proof.offers.slice(0,body.count),saveCount:body.count,version:1,status:'active',cadenceHours:body.cadenceHours||0};
    data.watches.unshift(w);result=w;
  }
  else if(path==='/shopping/items'&&method==='GET')result={items:data.items};
  else if(path==='/shopping/settings'){if(method==='PUT'){data.settings={...data.settings,...body};for(const item of data.items){item.quote=null;item.offers=[];item.priceStatus='unknown';}}result=data.settings;}
  else if(path==='/shopping/items'&&method==='POST'){const item={...body,id:id('item'),version:1,bought:null,quote:null,offers:[],priceStatus:'unknown'};data.items.push(item);result=item;}
  else if(path.startsWith('/shopping/items/')){const item=data.items.find(i=>i.id===path.split('/').at(-1));if(!item)error('Item not found.');if(method==='DELETE'){data.items=data.items.filter(i=>i!==item);result={ok:true};}else {const previous=JSON.stringify([item.name,item.brand||'',item.details||'',item.attributes||{}]);Object.assign(item,body,{version:item.version+1});if(previous!==JSON.stringify([item.name,item.brand||'',item.details||'',item.attributes||{}])){item.quote=null;item.offers=[];item.priceStatus='unknown';}result=item;}}
  else if(path==='/shopping/prices/status')result={latest:{status:'demo'}};
  else if(path==='/shopping/prices/refresh'||path==='/shopping/deals'){
    const items=data.items.filter(i=>!i.bought),strategy=body.strategy||'multi',stores=[...new Set(items.flatMap(i=>(i.offers||[]).map(o=>o.store)))];
    const ranked=stores.map(name=>{const quotes=items.map(item=>({item,o:(item.offers||[]).filter(o=>o.store===name).sort((a,b)=>a.priceMinor-b.priceMinor)[0]})).filter(x=>x.o);return {name,quotes,total:quotes.reduce((n,x)=>n+x.o.priceMinor*x.item.qty,0)};}).sort((a,b)=>b.quotes.length-a.quotes.length||a.total-b.total);
    const plan=[],unpriced=[];
    for(const item of items){const o=(item.offers||[]).filter(o=>strategy!=='single'||o.store===ranked[0]?.name).sort((a,b)=>a.priceMinor-b.priceMinor)[0];if(!o){unpriced.push(item);continue;}let group=plan.find(p=>p.store.name===o.store);if(!group){group={store:{id:o.store,name:o.store},lines:[],total:0};plan.push(group);}group.lines.push({item,qty:item.qty,price:o.priceMinor/100});group.total+=o.priceMinor*item.qty/100;}
    result={strategy,plan,totalMinor:Math.round(plan.reduce((n,p)=>n+p.total,0)*100),unpriced,mode:'demo',notice:'Compared fictional saved quotes only. No live search was performed.',diagnostics:[],storeCoverage:[],items:data.items};
  }
  else if(path==='/price-watches'&&method==='GET')result={items:data.watches};
  else if(path==='/price-watches'&&method==='POST'){const w={...body,id:id('watch'),version:1,status:'active',lastOffers:[],savedOptions:[],diagnostics:[],checkState:'idle'};data.watches.unshift(w);result=w;}
  else if(path.startsWith('/price-watches/')){const parts=path.split('/'),w=data.watches.find(w=>w.id===parts[2]);if(!w)error('Watch not found.');
   if(parts.includes('rotation'))error('Product media needs the Python backend and CLOUDINARY_URL. No media was generated.');
   if(parts[3]==='history')result={items:(w.savedOptions||[]).map(o=>({...o,at:o.checkedAt})),checks:[],notice:'Fictional preview observations only. Live history requires the backend.'};
   else if(parts[3]==='checks'){w.lastCheckedAt=new Date().toISOString();w.checkNotice='Static preview: no real API call was made. Start the backend to research this watch.';result={...w,offers:w.savedOptions||[],diagnostics:[],saveToken:JSON.stringify({spec:w,offers:w.savedOptions||[]}),mode:'demo'};}
   else if(parts[3]==='options'){if(!w.lastOffers.length)error('No preview options for this custom watch. Start the backend for live research.');w.savedOptions=w.lastOffers.slice(0,body.count);result=w;}
   else if(method==='DELETE'){data.watches=data.watches.filter(v=>v!==w);result={ok:true};}
   else{if(body.paused!==undefined)w.status=body.paused?'paused':'active';Object.assign(w,body,{version:w.version+1});result=w;}
  }
  else if(path.startsWith('/visual-previews'))error('Cloudinary previews need the Python backend, CLOUDINARY_URL and generation add-on access. No external API was called.');
  else if(path==='/research-searches')result={items:[]};
  else if(path==='/explore'){const search={...initial().searches[0],searchId:id('research'),query:body.query,kind:body.kind,mode:'demo',createdAt:new Date().toISOString(),notice:'These are fixed fictional events for previewing the layout. Start the backend to search real destinations.'};drafts.set(search.searchId,search);result=search;}
  else if(path==='/itineraries'&&method==='GET')result={items:data.trips};
  else if(path==='/itineraries'&&method==='POST'){const events=body.choices.map(c=>drafts.get(c.searchId)?.results.find(e=>e.id===c.resultId)).filter(Boolean);const trip={id:id('trip'),title:body.title,items:events,teasers:{},notice:'Fictional plan stored in this browser, not an account or booking.'};data.trips.unshift(trip);result=trip;}
  else if(path.startsWith('/itineraries/')){if(path.endsWith('/media'))error('Cloudinary generation needs the Python backend and CLOUDINARY_URL. No external API was called.');data.trips=data.trips.filter(t=>t.id!==path.split('/')[2]);result={ok:true};}
  else error('This action needs the Python backend.');
  save();return structuredClone(result);
 };
}
