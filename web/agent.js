import {renderCalendar} from '/calendar-view.js';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let current=null,polling=false,researchMode="demo";
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const d=await r.json();if(r.status===401){$('#shopping-workspace').hidden=true;$('#google-login').hidden=false;$('#logout').hidden=true;$('#account-title').textContent='Your plans, connected';$('#account-note').textContent='Sign in to save your plans.';setCalendarStatus(false);current=null;render([]);}if(!r.ok)throw Error(d.error||'Request failed');return d;}
function fail(e){$('#agent-error').textContent=e.message;$('#agent-error').hidden=false;}
function sources(result){return (result?.sources||[]).map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title||s.url)}</a>`).join('');}
function renderPlan(r){
 const groups=r.result?.groups||((r.result?.items||[]).length?[{category:'Shopping options',reason:'',items:r.result.items}]:[]);
 const products=groups.map(g=>`<section class="category"><div class="category-heading"><h3>${esc(g.category)}</h3><span class="badge">${g.items.length} ${g.items.length===1?'option':'alternatives'}</span></div><p class="hint">${esc(g.reason)}</p><div class="product-grid">${g.items.map(i=>`<article class="product"><span class="product-label">${r.mode==='demo'?'SAMPLE PRODUCT':'AMAZON.COM'}</span><h3>${esc(i.name)}</h3><div class="product-facts"><b>${i.price_cents===null?'Price unavailable':`$${(i.price_cents/100).toFixed(2)}`}</b><span>${i.rating==null?'Rating unavailable':`★ ${Number(i.rating).toFixed(1)} / 5`}<small>${i.review_count==null?'Review count unavailable':`${Number(i.review_count).toLocaleString()} reviews`}</small></span></div><p><b>Why it fits:</b> ${esc(i.reason)}</p><p class="hint">${i.uncertainties.map(esc).join(' ')}</p>${r.mode==='demo'?'<span class="demo-link">Sample item · not available to buy</span>':`<a class="buy-link" href="${esc(i.source_url)}" target="_blank" rel="noopener noreferrer">View item on Amazon</a>`}</article>`).join('')}</div></section>`).join('');
 const recipes=r.result?.recipes||[];
 return products+(recipes.length?`<section class="category"><div class="category-heading"><h3>Recipe ideas</h3><span class="badge">${recipes.length} ideas</span></div><p class="hint">Generated ideas. Prices and Amazon ratings apply only to linked ingredients, not recipes.</p><div class="product-grid">${recipes.map(recipe=>`<article class="product recipe"><span class="product-label">FOR THE TABLE</span><h3>${esc(recipe.name)}</h3><p>${esc(recipe.reason)}</p><details><summary>Ingredients & preparation</summary><ul>${recipe.ingredients.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><ol>${recipe.steps.map(x=>`<li>${esc(x)}</li>`).join('')}</ol></details>${r.mode==='live'?(recipe.ingredient_links||[]).map(l=>`<a class="text-link" href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.name)} on Amazon</a>`).join(''):''}<p class="hint">${esc(recipe.note)}</p></article>`).join('')}</div></section>`:'');
}

function render(runs){
 $('#conversation-messages').innerHTML=runs.length?runs.map(r=>`<div class="run-block">${r.messages.filter(m=>['user','assistant'].includes(m.role)).map(m=>`<div class="message ${esc(m.role)}"><span class="role">${m.role==='user'?'YOU':'UPNEXT'}${r.mode==='demo'&&m.role==='assistant'?' · SIMULATED':''}</span>${esc(m.content)}</div>`).join('')}${['queued','running'].includes(r.status)?'<p class="hint" role="status">Thinking through your occasion and comparing options…</p>':''}${renderPlan(r)}${r.result?`<details><summary>Evidence & missing information</summary><p class="hint">${r.result.missing_information.map(esc).join(' ')||'Check retailer details before buying.'}</p><div class="sources">${r.mode==='demo'?'<p class="hint">Demo sources are fictional and not purchase links.</p>':sources(r.result)}</div></details>`:''}${['completed','no_action'].includes(r.status)?(r.feedback?`<p class="hint">Feedback recorded: ${esc(r.feedback.value.replaceAll('_',' '))}.</p>`:`<div class="feedback"><button class="secondary" data-run="${esc(r.id)}" data-feedback="helpful">Helpful</button><button class="secondary" data-run="${esc(r.id)}" data-feedback="not_helpful">Not helpful</button><button class="secondary" data-run="${esc(r.id)}" data-feedback="dismissed">Dismiss</button></div>`):''}<div class="run-footer"><span>${esc(({completed:'Ready for your review',no_action:'You’re already covered',failed:'Couldn’t finish this plan',blocked:'Connection needed',interrupted:'Please try again',running:'Preparing your plan',queued:'Getting started'})[r.status]||r.status)}${r.mode==='demo'?' · Sample plan':''}</span><span>Saved to your plans</span></div></div>`).join(''):'<div class="empty"><h3>Start a new plan.</h3><p>Describe an occasion to see recommendations here.</p></div>';
 for(const b of document.querySelectorAll('[data-feedback]'))b.onclick=async()=>{b.disabled=true;try{await api('/api/agent/feedback',{run_id:b.dataset.run,value:b.dataset.feedback});await loadConversation();}catch(e){fail(e);b.disabled=false;}};
}
async function refreshConversations(){const d=await api('/api/agent/conversations');$('#conversation').innerHTML='<option value="">Start a new plan</option>'+d.conversations.map(c=>`<option value="${esc(c.id)}">${esc(c.title)}</option>`).join('');$('#conversation').value=current||'';
 const recent=await Promise.all(d.conversations.slice(0,12).map(c=>api(`/api/agent/conversations/${c.id}`)));
 const inbox=recent.flatMap(x=>x.runs).filter(r=>r.trigger==='proactive').slice(-5).reverse();$('#inbox').innerHTML=inbox.length?inbox.map(r=>`<p><button class="secondary" data-open="${r.conversation_id}">${esc(r.result?.summary||r.status)}</button></p>`).join(''):'<p class="hint">No upcoming suggestions yet.</p>';
 for(const b of document.querySelectorAll('[data-open]'))b.onclick=()=>{current=b.dataset.open;$('#conversation').value=current;loadConversation().catch(fail);};
}
async function loadConversation(){if(!current){render([]);return [];}const d=await api(`/api/agent/conversations/${current}`);render(d.runs);return d.runs;}
$('#conversation').onchange=()=>{current=$('#conversation').value||null;loadConversation().catch(fail);};
$('#new-conversation').onclick=()=>{if(polling)return;current=null;$('#conversation').value='';render([]);$('#message').focus();};
for(const b of document.querySelectorAll('[data-prompt]'))b.onclick=()=>{$('#message').value=b.dataset.prompt;$('#message').focus();};
$('#agent-form').onsubmit=async e=>{
 e.preventDefault();if(polling)return;polling=true;$('#research').disabled=true;$('#conversation').disabled=true;$('#new-conversation').disabled=true;$('#agent-error').hidden=true;
 try{const d=await api('/api/agent/runs',{message:$('#message').value,mode:researchMode,conversation_id:current,event_id:$('#event').value||null});current=d.conversation_id;$('#message').value='';await refreshConversations();
 const started=Date.now();for(;;){const runs=await loadConversation();const run=runs.find(r=>r.id===d.id);if(run&&!['queued','running'].includes(run.status))break;if(Date.now()-started>600000)throw Error('This run is still pending. You can return to this plan later.');await new Promise(r=>setTimeout(r,1200));}
 }catch(e){fail(e);}finally{polling=false;$('#research').disabled=false;$('#conversation').disabled=false;$('#new-conversation').disabled=false;}
};
$('#preferences-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/agent/preferences',{preferences:$('#personal-preferences').value,budget_cents:Math.round(Number($('#item-budget').value)*100)});$('#preferences-status').textContent='Saved. We’ll use these for your next recommendations.';}catch(e){fail(e);}};
function setCalendarStatus(connected){const status=$('#account-calendar-status');status.textContent=connected?'Google Calendar connected':'Google Calendar not connected';status.classList.toggle('connected',connected);}
async function refreshCalendar(){
 const cal=await api('/api/calendar');
 setCalendarStatus(cal.connected);
 renderCalendar(cal,event=>{if(polling)return;$('#event').value=event.id;$('#message').value=`Help me prepare for ${event.title} on ${event.date}. Consider what I already own and whether I need to buy anything.`;$('#agent-form').scrollIntoView({behavior:'smooth',block:'start'});$('#message').focus({preventScroll:true});});
 $('#connect-calendar').textContent=cal.connected?'Reconnect Google Calendar':'Connect Google Calendar';
 $('#sync-calendar').hidden=!cal.connected;$('#disconnect-calendar').hidden=!cal.connected;
 $('#event').innerHTML='<option value="">Choose an event, or tell us what’s coming up</option>'+cal.events.map(e=>`<option value="${esc(e.id)}">${esc(e.date)} · ${esc(e.title)}</option>`).join('');
 $('#calendar-note').textContent=cal.synced_at?`Last synced ${new Date(cal.synced_at).toLocaleString()}.`:cal.connected?'Calendar connected. Sync to load your upcoming events.':'Connect your calendar, or describe an occasion below.';
 return cal;
}
$('#logout').onclick=async()=>{try{await api('/auth/logout',{});location.href='/';}catch(e){$('#connection-message').textContent=e.message;}};
$('#sync-calendar').onclick=async()=>{const b=$('#sync-calendar');b.disabled=true;$('#sync-status').textContent='Syncing your upcoming events… This can take a few minutes.';try{await api('/api/calendar/sync',{});await refreshCalendar();$('#sync-status').textContent='Your calendar is up to date.';}catch(e){$('#sync-status').textContent=e.message;}finally{b.disabled=false;}};
$('#disconnect-calendar').onclick=async()=>{try{await api('/api/calendar/disconnect',{});await refreshCalendar();$('#sync-status').textContent='Disconnected. Saved plans remain in your account. You can also revoke UpNext in your Google Account settings.';}catch(e){$('#sync-status').textContent=e.message;}};
async function init(){
 const account=await api('/auth/me');
 if(!account.user){$('#shopping-workspace').hidden=true;$('#google-login').hidden=!account.configured;$('#account-note').textContent=account.configured?'Sign in to save your plans. You can connect Calendar afterward.':'Google sign-in is being set up by the app owner. Please check back soon.';return;}
 $('#account-title').textContent=`Welcome${account.user.name?', '+account.user.name:''}`;$('#account-note').textContent=account.user.email;$('#google-login').hidden=true;$('#logout').hidden=false;$('#shopping-workspace').hidden=false;

 const s=await api('/api/agent/status');researchMode=s.live_available?'live':'demo';$('#preview-notice').hidden=s.live_available;$('#item-budget').value=(s.settings.budget_cents/100).toFixed(2);$('#personal-preferences').value=s.settings.preferences;$('#profile-summary').textContent='A few details help us suggest things that suit you.';
 await refreshCalendar();
 await refreshConversations();
}
const connection=new URLSearchParams(location.search).get('connection');
if(connection==='failed')$('#connection-message').textContent='Google connection wasn’t completed. Try again, use the same Google account, and approve the requested access.';
if(connection==='calendar')$('#connection-message').textContent='Calendar connected. Select Sync calendar to load your events.';
if(connection)history.replaceState(null,'','/');
init().catch(e=>{$('#connection-message').textContent=e.message;});
