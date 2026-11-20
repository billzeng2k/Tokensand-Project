const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const dateOnly=value=>new Date(`${value}T12:00:00`);
const dayKey=value=>`${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}-${String(value.getDate()).padStart(2,'0')}`;
let data,anchor,selectEvent,mode='four-weeks',counts={};
const root=()=>document.querySelector('#calendar-view');
function onDay(event,day){const end=event.end?.date||event.end?.dateTime?.slice(0,10)||event.date;return event.date<=day&&(event.end?.date?day<end:day<=end);}
function draw(){
 if(!data||!root())return;
 const first=new Date(anchor);
 const days=Array.from({length:mode==='four-weeks'?28:7},(_,i)=>{const d=new Date(first);d.setDate(d.getDate()+i);return d;});
 root().innerHTML=`<div class="calendar-toolbar"><h2>${esc(first.toLocaleDateString(undefined,{month:'short',day:'numeric'})+' – '+days.at(-1).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'}))}</h2><div><button class="secondary" id="calendar-today">Today</button><button class="secondary" id="calendar-prev" aria-label="Previous ${mode}">‹</button><button class="secondary" id="calendar-next" aria-label="Next ${mode}">›</button><select id="calendar-mode" aria-label="Calendar view"><option value="week" ${mode==='week'?'selected':''}>7 days</option><option value="four-weeks" ${mode==='four-weeks'?'selected':''}>4 weeks</option></select></div></div><div class="calendar-board ${mode}">${days.map(d=>{
 const key=dayKey(d),items=data.events.filter(e=>onDay(e,key)),live=items.reduce((n,e)=>n+(counts[e.id]?.live||0),0),demo=items.reduce((n,e)=>n+(counts[e.id]?.demo||0),0);
 return `<section class="calendar-column ${key===data.window_start?'is-today':''} ${key<data.window_start||key>data.window_end?'out-of-range':''}" aria-label="${esc(d.toLocaleDateString(undefined,{dateStyle:'full'}))}"><header><span>${d.toLocaleDateString(undefined,{weekday:'short'})}</span><strong>${d.getDate()}</strong><p>${items.length} ${items.length===1?'event':'events'}<br>${live} recommended purchases${demo?`<br><span class="sample-count">${demo} sample ${demo===1?'option':'options'}</span>`:''}</p></header><div class="calendar-event-list" tabindex="0" aria-label="Events for ${key}">${items.map(e=>`<button class="calendar-event ${esc(e.kind)}" data-event="${esc(e.id)}"><span>${e.date<key?'Continues':e.all_day?'All day':esc(e.start?.dateTime?.slice(11,16)||'')}</span><b>${esc(e.title)}</b>${counts[e.id]?.live?`<small>${counts[e.id].live} recommended purchases</small>`:''}${counts[e.id]?.demo?`<small>${counts[e.id].demo} sample options</small>`:''}</button>`).join('')}</div></section>`;
 }).join('')}</div>${!data.events.length?`<p class="calendar-empty">${data.connected?'Sync your calendar using the Connected menu to load events.':'Connect Google Calendar using the card in the sidebar.'}</p>`:''}<details class="calendar-info"><summary>Calendar details</summary><p>${esc(data.note)}</p><p>Counts use the latest completed plan for each event. Product alternatives are counted individually; recipes are excluded. Times retain their calendar timezone. Events spanning days appear on each day.</p>${data.warnings.map(w=>`<p>${esc(w)}</p>`).join('')}</details>`;
 root().querySelectorAll('[data-event]').forEach(b=>b.onclick=()=>selectEvent(data.events.find(e=>e.id===b.dataset.event)));
 root().querySelector('#calendar-mode').onchange=e=>{mode=e.target.value;draw();};
 function move(n){anchor.setDate(anchor.getDate()+(mode==='week'?7:28)*n);if(dayKey(anchor)<data.window_start)anchor=dateOnly(data.window_start);draw();}
 root().querySelector('#calendar-prev').onclick=()=>move(-1);
 root().querySelector('#calendar-next').onclick=()=>move(1);
 root().querySelector('#calendar-today').onclick=()=>{anchor=dateOnly(data.window_start);draw();};
 const previous=new Date(anchor),next=new Date(anchor);previous.setDate(previous.getDate()-1);next.setDate(next.getDate()+(mode==='week'?7:28));
 root().querySelector('#calendar-prev').disabled=dayKey(previous)<data.window_start;
 root().querySelector('#calendar-next').disabled=dayKey(next)>data.window_end;
}
export function renderCalendar(calendar,onSelect){data={warnings:[],events:[],...calendar};selectEvent=onSelect;if(!anchor)anchor=dateOnly(data.window_start);draw();}
export function updateRecommendationCounts(value){counts=value;draw();}
