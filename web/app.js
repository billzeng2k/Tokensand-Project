const $=s=>document.querySelector(s),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let report=null;
const labels={task_saved:'Your shopping task is saved.',already_saved:'You’re already covered.',event_cancelled:'This occasion was cancelled.',no_eligible_product:'Nothing meets every requirement.',action_unconfirmed:'We couldn’t confirm the task was saved.',tool_error:'A service needs attention.'};
$('#scenario').onchange=()=>{if($('#scenario').value!=='happy')$('#mode').value='isolated';};
$('#mode').onchange=()=>{if($('#mode').value==='integration')$('#scenario').value='happy';};
function render(r){report=r;$('#download').disabled=false;const t=r.task;$('#result').innerHTML=`<span class="pill">${esc(r.memory_backend)} memory · ${esc(r.storage_backend)} storage</span><h2>${esc(labels[r.status]||r.status)}</h2>${t?`<div class="task"><strong>${esc(t.product.name)} · $${(t.product.price_cents/100).toFixed(2)}</strong>Review before ${esc(t.deadline)}. Item price only.<br>No order has been placed.</div>`:'<p>Check the decision trail below. The agent has not placed an order.</p>'}<p class="note">Run ${esc(r.run_id)} · ${r.steps.length} recorded steps</p>`;const decisions=r.decisions||[];$('#trail').innerHTML=decisions.map(d=>`<div class="decision"><div><b>${esc(d.product.name)}</b><p class="muted">${esc(d.product.source)}</p></div><div class="${d.reasons.length?'bad':'good'}">${d.reasons.length?d.reasons.map(s=>esc(s.replaceAll('_',' '))).join('<br>'):'Eligible at initial check'}</div></div>`).join('')+`<details><summary>Retrieved memory evidence</summary><pre>${esc(r.memory_evidence)}</pre></details><details open><summary>Tool calls and verified results</summary><pre>${esc(JSON.stringify(r.steps,null,2))}</pre></details>`;}
$('#run-form').onsubmit=async e=>{e.preventDefault();$('#run').disabled=true;$('#download').disabled=true;report=null;$('#trail').innerHTML='<p class="muted">Waiting for this run’s evidence.</p>';$('#result').innerHTML='<span class="pill">Working</span><h2>Checking the occasion<br>and your preferences…</h2><p>Local model startup can take a moment. The audit will show the actual results.</p>';try{const response=await fetch('/api/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario:$('#scenario').value,mode:$('#mode').value,event_id:$('#calendar-event').value||undefined})});const data=await response.json();if(!response.ok)throw Error(data.error);for(;;){await new Promise(r=>setTimeout(r,1000));const poll=await fetch(`/api/runs/${data.id}`);if(!poll.ok)throw Error('Could not read run status.');const job=await poll.json();if(job.state==='failed')throw Error(job.error);if(job.state==='complete'){render(job.report);break;}}}catch(error){$('#result').innerHTML=`<span class="pill">Run unavailable</span><h2>Let’s check the local services.</h2><p>${esc(error.message)}</p><p>Try isolated mode to test without Cognee or SingleStore.</p>`;}finally{$('#run').disabled=false;}};
$('#download').onclick=()=>{if(!report)return;const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`tokensand-audit-${report.run_id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};

let calendarEvents=[];
function showCalendar(data){
 calendarEvents=data.events;
 const previous=$('#calendar-event').value;
 $('#calendar-event').innerHTML='<option value="">Demo holiday dinner</option>'+data.events.map(e=>`<option value="${esc(e.id)}">${esc(e.date)} · ${esc(e.title)}</option>`).join('');
 if(data.events.some(e=>e.id===previous))$('#calendar-event').value=previous;
 $('#calendar-status').textContent=(data.synced_at?`Last sync: ${new Date(data.synced_at).toLocaleString()}. `:'No successful sync yet. ')+(data.connected?'': 'Run npm run calendar:connect first. ')+data.note;
 $('#calendar-event').dispatchEvent(new Event('change'));
}
$('#calendar-event').onchange=()=>{
 const e=calendarEvents.find(e=>e.id===$('#calendar-event').value);
 $('#occasion-title').textContent=e?e.title:'Holiday dinner';
 $('#occasion-date').textContent=e?e.date:'December 4, 2026';
 $('#scenario').disabled=!!e;if(e)$('#scenario').value='happy';
};
$('#calendar-sync').onclick=async()=>{
 $('#calendar-sync').disabled=true;$('#run').disabled=true;
 $('#calendar-status').textContent='Syncing read-only events through Airbyte…';
 try{
  const response=await fetch('/api/calendar/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  const data=await response.json();if(!response.ok)throw Error(data.error);
  for(;;){await new Promise(r=>setTimeout(r,1000));const response=await fetch(`/api/runs/${data.id}`);const job=await response.json();if(!response.ok||job.state==='failed')throw Error(job.error);if(job.state==='complete'){showCalendar(job.calendar);break;}}
 }catch(e){$('#calendar-status').textContent=e.message;}finally{$('#calendar-sync').disabled=false;$('#run').disabled=false;}
};
fetch('/api/calendar').then(r=>{if(!r.ok)throw Error('Calendar status unavailable');return r.json();}).then(showCalendar).catch(e=>{$('#calendar-status').textContent=e.message;});
