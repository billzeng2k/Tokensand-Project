import {renderCalendar,updateRecommendationCounts} from '/calendar-view.js';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let drafts={};
const thumbnailRefreshes=new Set();
let allRuns=[],events=[],selectedEvent=null,current=null,researchMode='demo',shopping={decisions:[],notes:[]},authenticated=false,pollTimer=null,submitting=false;
const pending=r=>['queued','running'].includes(r.status);
const itemKey=url=>url.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})(?:[/?#]|$)/i)?.[1].toUpperCase()||url;
const eventRuns=id=>allRuns.filter(r=>r.event_id===id).sort((a,b)=>a.created_at.localeCompare(b.created_at)||a.id.localeCompare(b.id));
async function api(path,body){const response=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const data=await response.json();if(response.status===401){authenticated=false;$('#shopping-workspace').hidden=true;$('#google-login').hidden=false;$('#connection-message').textContent='Sign in again to continue.';}if(!response.ok)throw Error(data.error||'Request failed');return data;}
function fail(error){$('#agent-error').textContent=error.message;$('#agent-error').hidden=false;}
function announce(text){$('#action-status').textContent=text;}
function hiddenItem(item,eventId){const key=itemKey(item.source_url);return shopping.decisions.some(d=>d.item_key===key&&(d.action==='purchased'||d.event_id===eventId));}
function combinedPlan(eventId){
 const runs=eventRuns(eventId).filter(r=>r.result&&['completed','no_action'].includes(r.status));
 const live=runs.filter(r=>r.mode==='live'),eligible=live.length?live:runs,items=new Map();
 for(const run of eligible){for(const group of run.result.groups||[]){for(const item of group.items){const key=itemKey(item.source_url),image=item.image_url||shopping.images?.[key]?.image_url||items.get(key)?.image_url;items.set(key,{...item,image_url:image,_run_id:run.id,category:group.category,category_reason:group.reason});}}}
 const groups=new Map();for(const item of items.values()){if(hiddenItem(item,eventId))continue;if(!groups.has(item.category))groups.set(item.category,{category:item.category,reason:item.category_reason,items:[]});groups.get(item.category).items.push(item);}
 return {mode:live.length?'live':'demo',result:{groups:[...groups.values()],recipes:[]}};
}
function renderPlan(r){
 const groups=r.result?.groups||((r.result?.items||[]).length?[{category:'Shopping options',reason:'',items:r.result.items}]:[]);
 const products=groups.map(g=>`<section class="category ${g.items.length===1?'single-item-category':''}"><div class="category-heading"><h3>${esc(g.category)}</h3><span class="badge">${g.items.length} ${g.items.length===1?'option':'alternatives'}</span></div><p class="hint">${esc(g.reason)}</p><div class="product-grid">${g.items.map(i=>`<article class="product">${i.image_url?`<img class="product-thumbnail" src="${esc(i.image_url)}" alt="${esc(i.name)}" loading="lazy" referrerpolicy="no-referrer">`:`<div class="product-thumbnail thumbnail-placeholder">${shopping.images?.[itemKey(i.source_url)]?.status==='unavailable'?'Image unavailable':'Loading image…'}</div>`}<span class="product-label">${r.mode==='demo'?'SAMPLE PRODUCT':'AMAZON.COM'}</span><h3>${esc(i.name)}</h3>${i.variant?`<p class="product-variant">${esc(i.variant)}</p>`:``}<div class="product-facts"><b>${i.price_cents===null?'Price unavailable':`$${(i.price_cents/100).toFixed(2)}`}</b><span>${i.rating==null?'Rating unavailable':`★ ${Number(i.rating).toFixed(1)} / 5`}${i.review_count==null?'':`<small>${Number(i.review_count).toLocaleString()} reviews</small>`}</span></div><p><b>Why it fits:</b> ${esc(i.reason)}</p><p class="hint">${i.uncertainties.filter(note=>note.trim()!=='Price, rating, stock and delivery must be rechecked on Amazon before buying.').map(esc).join(' ')}</p>${r.mode==='demo'?'<span class="demo-link">Sample item · not available to buy</span>':`<a class="buy-link" href="${esc(i.source_url)}" target="_blank" rel="noopener noreferrer">View item on Amazon</a>`}${r.mode==='live'?`<div class="item-actions"><button class="item-check" data-item-action="purchased" data-run="${esc(i._run_id||r.id)}" data-url="${esc(i.source_url)}" aria-label="Mark ${esc(i.name)} as purchased" title="Mark as purchased">✓ <span>Purchased</span></button><button class="item-dismiss" data-item-action="dismissed" data-run="${esc(i._run_id||r.id)}" data-url="${esc(i.source_url)}" aria-label="Don’t buy ${esc(i.name)}" title="Don’t buy this">× <span>Not for me</span></button></div>`:''}</article>`).join('')}</div></section>`).join('');
 return `<div class="recommendation-categories">${products}</div>`;
}
function progress(run){const span=[...(run.spans||[])].reverse().find(s=>s.status==='running');if(span?.name.includes('recommendation'))return 'Writing your recommendations…';if(span?.name.includes('research.plan'))return 'Planning the Amazon search…';if(span?.name.includes('airbyte'))return 'Checking your calendar…';if((run.local_research_audit||[]).length)return 'Reading Amazon products…';return run.status==='queued'?'Your request is queued…':'Searching Amazon for your event…';}
function renderChat(runs){
 const panel=$('#event-chat-messages'),atBottom=panel.scrollHeight-panel.scrollTop-panel.clientHeight<80;
 panel.innerHTML=runs.length?runs.map(r=>`${r.messages.filter(m=>['user','assistant'].includes(m.role)).map(m=>`<div class="chat-message ${esc(m.role)}"><span>${m.role==='user'?'You':'UpNext'}</span><p>${esc(m.content)}</p></div>`).join('')}${pending(r)?`<div class="chat-progress" role="status"><i></i>${esc(progress(r))}</div>`:''}`).join(''):'<div class="chat-welcome"><h3>What do you need for this event?</h3><p>Ask for ideas or something specific. New finds will be added to your recommendations.</p><button class="secondary" id="start-research">Find recommendations</button></div>';
 if(atBottom)panel.scrollTop=panel.scrollHeight;
 const start=$('#start-research');if(start)start.onclick=()=>{$('#message').value=`Suggest useful purchases for ${selectedEvent.title}. Consider what I already own.`;$('#agent-form').requestSubmit();};
 $('#research').disabled=submitting||runs.some(pending);$('#research').textContent=runs.some(pending)?'Researching…':'Send';
}
function renderMemory(){
 const purchased=shopping.decisions.filter(d=>d.action==='purchased');
 $('#memory-list').innerHTML=`<p class="hint">${purchased.length} item${purchased.length===1?'':'s'} marked purchased. Dismissed items are skipped for this event only.</p>`+(shopping.notes.length?shopping.notes.map(n=>`<div class="memory-note"><span>${esc(n.text)}</span><button class="text-button" data-forget="${esc(n.id)}" aria-label="Forget ${esc(n.text)}">Forget</button></div>`).join(''):'<p class="hint">Check “Remember this” when you share a preference in chat.</p>');
}
function renderHistory(){
 const rows=shopping.decisions.filter(d=>d.action==='purchased');
 $('#purchased-items').innerHTML=rows.length?rows.map(d=>`<article class="purchase-row">${(d.item.image_url||shopping.images?.[d.item_key]?.image_url)?`<img src="${esc(d.item.image_url||shopping.images?.[d.item_key]?.image_url)}" alt="${esc(d.item.name)}" referrerpolicy="no-referrer">`:''}<div><h3>${esc(d.item.name)}</h3><p>${esc(d.item.variant||'')}</p><p class="hint">${esc(d.event_title)} · Marked purchased ${new Date(d.updated_at).toLocaleDateString()}</p><a href="${esc(d.item.source_url)}" target="_blank" rel="noopener noreferrer">View on Amazon</a><p class="hint">${d.item.price_cents==null?'Price unavailable':`Listed at $${(d.item.price_cents/100).toFixed(2)}`} · Marked by you, not a checkout receipt</p></div><button class="secondary" data-item-action="undo" data-run="${esc(d.run_id)}" data-url="${esc(d.item.source_url)}">Undo</button></article>`).join(''):'<div class="empty"><h3>No purchases yet</h3><p>Use the ✓ on a recommendation after you’ve purchased it.</p></div>';
}
function renderWorkspace(){
 const counts={};for(const event of events){const plan=combinedPlan(event.id),count=plan.result.groups.reduce((n,g)=>n+g.items.length,0);counts[event.id]={live:plan.mode==='live'?count:0,demo:plan.mode==='demo'?count:0};}updateRecommendationCounts(counts);
 renderMemory();renderHistory();
 if(!selectedEvent)return;
 const runs=eventRuns(selectedEvent.id),plan=combinedPlan(selectedEvent.id);
 $('#event-recommendations').innerHTML=plan.result.groups.length?renderPlan(plan):'<div class="empty"><h3>Make a plan for this event</h3><p>Your recommendations will appear here. Ask UpNext in the chat to get started.</p></div>';
 const dismissed=shopping.decisions.filter(d=>d.action==='dismissed'&&d.event_id===selectedEvent.id);$('#dismissed-items').hidden=!dismissed.length;
 $('#dismissed-list').innerHTML=dismissed.map(d=>`<div class="dismissed-row"><span>${esc(d.item.name)}</span><button class="text-button" data-item-action="undo" data-run="${esc(d.run_id)}" data-url="${esc(d.item.source_url)}">Restore</button></div>`).join('');
 renderChat(runs);refreshThumbnails();
}
function mergeRuns(runs){const map=new Map(allRuns.map(r=>[r.id,r]));for(const r of runs)map.set(r.id,r);allRuns=[...map.values()];}
async function refreshRuns(){const d=await api('/api/agent/conversations');const conversations=await Promise.all(d.conversations.map(c=>api(`/api/agent/conversations/${c.id}`)));allRuns=conversations.flatMap(c=>c.runs);renderWorkspace();schedulePoll();}
function schedulePoll(){if(pollTimer||!authenticated||!allRuns.some(pending))return;pollTimer=setTimeout(pollPending,1500);}
async function pollPending(){pollTimer=null;if(!authenticated)return;try{const runs=await Promise.all(allRuns.filter(pending).map(r=>api(`/api/agent/runs/${r.id}`)));mergeRuns(runs);renderWorkspace();}catch(error){fail(new Error(`Could not refresh progress: ${error.message}. Retrying automatically.`));}finally{schedulePoll();}}
$('#agent-form').onsubmit=async event=>{
 event.preventDefault();if(submitting||!selectedEvent||eventRuns(selectedEvent.id).some(pending))return;
 const message=$('#message').value.trim();if(!message)return;
 const eventId=selectedEvent.id,conversationId=current;
 submitting=true;$('#research').disabled=true;$('#agent-error').hidden=true;
 try{
  if($('#remember-message').checked){shopping=await api('/api/agent/memory',{text:message});$('#remember-message').checked=false;announce('Preference remembered.');}
  const run=await api('/api/agent/runs',{message,mode:researchMode,conversation_id:conversationId,event_id:eventId});if(selectedEvent?.id===eventId){current=run.conversation_id;$('#message').value='';}drafts[eventId]='';mergeRuns([await api(`/api/agent/runs/${run.id}`)]);schedulePoll();
 }catch(error){fail(error);}finally{submitting=false;renderWorkspace();}
};
document.addEventListener('click',async event=>{
 const action=event.target.closest('[data-item-action]'),forget=event.target.closest('[data-forget]');if(!action&&!forget)return;
 const button=action||forget;button.disabled=true;
 try{shopping=await api(action?'/api/agent/item-action':'/api/agent/memory',action?{run_id:action.dataset.run,source_url:action.dataset.url,action:action.dataset.itemAction}:{action:'forget',id:forget.dataset.forget});renderWorkspace();announce(forget?'Preference forgotten.':action.dataset.itemAction==='purchased'?'Marked purchased. Saved to purchase history.':action.dataset.itemAction==='dismissed'?'Removed for this event. You can restore it below.':'Restored.');}catch(error){fail(error);button.disabled=false;}
});
function setCalendarStatus(connected){$('#account-calendar-status').textContent=connected?'Connected':'Disconnected';$('#account-panel').classList.toggle('calendar-connected',connected);}
async function refreshCalendar(){const cal=await api('/api/calendar');events=cal.events;setCalendarStatus(cal.connected);renderCalendar(cal,openCalendarEvent);$('#sync-calendar').hidden=!cal.connected;$('#disconnect-calendar').hidden=!cal.connected;$('#connect-calendar').textContent=cal.connected?'Reconnect Google Calendar':'Connect Google Calendar';route();return cal;}
function openCalendarEvent(event){location.hash=`event-details/${event.id}`;route();}
function route(){
 const isSettings=location.hash==='#settings',isHistory=location.hash==='#saved-plans',match=location.hash.match(/^#event-details\/([a-f0-9]{64})$/),detail=!!match;
 const nextEvent=match?events.find(e=>e.id===match[1])||null:null;
 if(selectedEvent?.id!==nextEvent?.id){if(selectedEvent)drafts[selectedEvent.id]=$('#message').value;$('#message').value=nextEvent?(drafts[nextEvent.id]||''):'';}
 selectedEvent=nextEvent;
 $('#settings-page').hidden=!isSettings;$('#calendar-page').hidden=isHistory||detail||isSettings;$('#history-page').hidden=!isHistory;$('#event-page').hidden=!detail;$('.page-heading').hidden=true;document.body.classList.toggle('calendar-screen',!isHistory&&!detail&&!isSettings);
 $('.event-workspace').hidden=detail&&!selectedEvent;
 if(detail){$('#event-title').textContent=selectedEvent?.title||'Event not found';$('#event-date').textContent=selectedEvent?`${selectedEvent.date} · ${selectedEvent.all_day?'All day':(selectedEvent.start?.dateTime?.slice(11,16)||'')+' '+(selectedEvent.start?.timeZone||'')}`:'This event is no longer in your synced calendar. Return to Calendar or sync again.';current=selectedEvent?eventRuns(selectedEvent.id).at(-1)?.conversation_id||null:null;}
 for(const link of document.querySelectorAll('.sidebar .nav')){const active=link.hash===(isSettings?'#settings':isHistory?'#saved-plans':'#calendar-view');link.classList.toggle('active',active);if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');}
 renderWorkspace();schedulePoll();refreshThumbnails();
}
window.addEventListener('hashchange',route);
const calendarMenu=$('#calendar-account-menu'),calendarToggle=$('#calendar-menu-toggle');
function closeCalendarMenu(){calendarMenu.hidden=true;calendarToggle.setAttribute('aria-expanded','false');}
calendarToggle.onclick=()=>{calendarMenu.hidden=!calendarMenu.hidden;calendarToggle.setAttribute('aria-expanded',String(!calendarMenu.hidden));};
document.addEventListener('click',event=>{if(!$('#account-panel').contains(event.target))closeCalendarMenu();});document.addEventListener('keydown',event=>{if(event.key==='Escape')closeCalendarMenu();});
$('#logout').onclick=async()=>{try{await api('/auth/logout',{});location.href='/';}catch(error){fail(error);}};
$('#sync-calendar').onclick=async()=>{const button=$('#sync-calendar');button.disabled=true;$('#sync-status').textContent='Syncing calendar…';try{await api('/api/calendar/sync',{});await refreshCalendar();$('#sync-status').textContent='Calendar synced. Checking for new recommendations…';}catch(error){$('#sync-status').textContent=error.message;}finally{button.disabled=false;}};
$('#disconnect-calendar').onclick=async()=>{try{await api('/api/calendar/disconnect',{});await refreshCalendar();$('#sync-status').textContent='Disconnected. Your saved purchases remain.';}catch(error){fail(error);}};
async function init(){const account=await api('/auth/me');if(!account.user){$('#google-login').hidden=!account.configured;$('#account-note').textContent='Sign in to save your plans and purchases.';return;}authenticated=true;$('#account-title').textContent=account.user.name;$('#account-note').textContent=account.user.email;$('#google-login').hidden=true;$('#logout').hidden=false;$('#shopping-workspace').hidden=false;const status=await api('/api/agent/status');researchMode=status.live_available?'live':'demo';$('#provider-note').textContent=status.provider==='ollama-local'?'Local Qwen':'UpNext';shopping=await api('/api/agent/shopping');await refreshCalendar();await refreshRuns();await loadAutomation();route();}
init().catch(fail);

async function refreshThumbnails(){
 if(!selectedEvent||thumbnailRefreshes.has(selectedEvent.id))return;
 const plan=combinedPlan(selectedEvent.id);
 if(plan.mode!=='live'||!plan.result.groups.some(g=>g.items.some(i=>!i.image_url)))return;
 const id=selectedEvent.id;thumbnailRefreshes.add(id);
 try{shopping=await api('/api/agent/thumbnails',{event_id:id});renderWorkspace();}
 catch(error){announce('Some product images could not be loaded. Reload to retry.');}
}

function showAutomation(data){const cfg=data.settings;$('#automation-enabled').checked=cfg.enabled;$('#automation-time').value=cfg.time;$('#automation-zone').value=cfg.timezone;$('#automation-days').value=cfg.lookahead_days;$('#automation-last').textContent=data.last_run?`Last run: ${data.last_run.status} · ${data.last_run.runs_created} events researched`:'No scheduled run yet.';}
async function loadAutomation(){showAutomation(await api('/api/agent/automation'));}
$('#automation-form').onsubmit=async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{showAutomation(await api('/api/agent/automation',{enabled:$('#automation-enabled').checked,time:$('#automation-time').value,timezone:$('#automation-zone').value,lookahead_days:Number($('#automation-days').value)}));$('#automation-status').textContent='Schedule saved.';}catch(error){$('#automation-status').textContent=error.message;}finally{button.disabled=false;}};

// Background calendar research can start without a chat message or an open event.
setInterval(async()=>{if(!authenticated||document.hidden||allRuns.some(pending))return;try{await refreshRuns();if(location.hash==='#settings')await loadAutomation();}catch(error){fail(error);}},15000);
