"""Local app/admin API and opt-in calendar scheduler; no public-hosting support."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime,timezone,timedelta
import hashlib
import hmac
from http.cookies import SimpleCookie
import json
import os
import secrets
import threading
import time
from urllib.parse import urlparse,parse_qs
from . import observability as ledger
from . import agent, tenancy, auth

POOL=ThreadPoolExecutor(max_workers=1)
SCAN_LOCK=threading.Lock()
STOP=threading.Event()
SESSIONS={}
QUEUE_LOCK=threading.Lock()
ACTIVE=set()
LAST_SCAN=0


def admin_allowed(handler):
    token=os.getenv('UPNEXT_ADMIN_TOKEN','')
    if not token:return False
    cookies=SimpleCookie()
    try:cookies.load(handler.headers.get('Cookie',''))
    except Exception:return False
    sid=cookies.get('upnext_admin')
    return bool(sid and SESSIONS.get(sid.value,0)>time.time())


def status():
    local=os.getenv('UPNEXT_LLM_PROVIDER')=='ollama'
    return {'provider':'ollama-local' if local else 'openai-responses-web-search','live_available':local or bool(os.getenv('OPENAI_API_KEY')),
            'model':os.getenv('OLLAMA_MODEL','qwen3:14b') if local else os.getenv('OPENAI_MODEL','gpt-6.2-astra'),'amplitude_mode':os.getenv('AMPLITUDE_MODE','local'),
            'statsig_mode':os.getenv('STATSIG_MODE','local'),'admin_auth_configured':bool(os.getenv('UPNEXT_ADMIN_TOKEN')),
            'storage':'local SQLite trace ledger','settings':{k:v for k,v in ledger.settings().items() if k in ('agent_enabled','web_enabled','proactive_enabled','proactive_mode','budget_cents','memory_backend','preferences')}}


def submit(prompt,mode,cid=None,trigger='manual',event_id=None):
    with QUEUE_LOCK:
        if len(ACTIVE)>=4:raise ValueError('Queue is full. Wait for a run to finish.')
        run=ledger.create_run(prompt,mode,cid,trigger,event_id);ACTIVE.add(run['id'])
    def work():
        try:agent.execute(run['id'])
        finally:
            with QUEUE_LOCK:ACTIVE.discard(run['id'])
    tenancy.enqueue(POOL,work)
    return run


def scan():
    global LAST_SCAN
    if not SCAN_LOCK.acquire(blocking=False):return {'status':'busy'}
    LAST_SCAN=time.monotonic()
    result={'status':'completed','eligible_events':0,'duplicate_suppressed':0,'runs_created':0,'run_ids':[]}
    try:
        settings=ledger.settings()
        if not settings['proactive_enabled'] or not settings['agent_enabled']:
            return ledger.record_scan({**result,'status':'paused'})
        from .calendar import sync
        snapshot=sync() # No fixture fallback and no using stale snapshots.
        today=date.today();end=today+timedelta(days=settings['lookahead_days'])
        events=[e for e in snapshot['events'] if today<=date.fromisoformat(e['date'])<=end]
        result['eligible_events']=len(events)
        existing=sum(r['trigger']=='proactive' and r['created_at'][:10]==datetime.now(timezone.utc).date().isoformat() for r in ledger.query(days=2))
        for event in events:
            if result['runs_created']>=min(2,max(0,settings['max_daily_runs']-existing)):break
            key=hashlib.sha256(json.dumps([event['id'],event.get('updated'),settings['proactive_mode'],'proactive-v1']).encode()).hexdigest()
            if not ledger.reserve_trigger(key):result['duplicate_suppressed']+=1;continue
            run=ledger.create_run('Check this upcoming occasion. Suggest a purchase only if it addresses a concrete need; consider reusing owned items first.',settings['proactive_mode'],trigger='proactive',event_id=event['id'])
            result['run_ids'].append(run['id']);result['runs_created']+=1
            with ledger.db() as c:c.execute('UPDATE triggers SET run_id=? WHERE id=?',(run['id'],key))
            agent.execute(run['id'])
        return ledger.record_scan(result)
    except Exception as exc:return ledger.record_scan({**result,'status':'failed','error_code':agent.error_code(exc)})
    finally:SCAN_LOCK.release()


def scheduler():
    last = {}
    while not STOP.wait(15):
        for uid in [None] + [u['id'] for u in auth.users()]:
            with tenancy.scope(uid):
                settings = ledger.settings()
                if settings['proactive_enabled'] and time.monotonic()-last.get(uid,0)>=settings['interval_minutes']*60:
                    last[uid]=time.monotonic()
                    tenancy.enqueue(POOL,scan)


def ensure_admin_token():
    from .config import LOCAL
    if os.getenv('UPNEXT_ADMIN_TOKEN'):return os.environ['UPNEXT_ADMIN_TOKEN']
    path=LOCAL/'admin-token'
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(32))
    except FileExistsError:pass
    os.environ['UPNEXT_ADMIN_TOKEN']=path.read_text().strip()
    return os.environ['UPNEXT_ADMIN_TOKEN']


def startup():
    for uid in [None] + [u['id'] for u in auth.users()]:
        with tenancy.scope(uid):ledger.recover()
    threading.Thread(target=scheduler,name='upnext-calendar-scheduler',daemon=True).start()


def get(handler,path):
    if not path.startswith(('/api/agent/','/api/admin/')):return False
    admin=path.startswith('/api/admin/')
    if admin and not admin_allowed(handler):handler.send({'error':'Admin sign-in required'},401);return True
    if path=='/api/admin/users':handler.send({'users':auth.users()})
    elif path=='/api/agent/status':handler.send(status())
    elif path=='/api/agent/conversations':handler.send({'conversations':ledger.conversations()})
    elif path.startswith('/api/agent/conversations/'):
        handler.send({'runs':ledger.conversation(path.rsplit('/',1)[-1])})
    elif path.startswith(('/api/agent/runs/','/api/admin/runs/')):
        run=ledger.get(path.rsplit('/',1)[-1]);handler.send(run or {'error':'Not found'},200 if run else 404)
    elif path=='/api/admin/metrics':
        query=parse_qs(urlparse(handler.path).query);mode=query.get('mode',['all'])[0]
        try:days=int(query.get('days',['30'])[0])
        except ValueError:days=0
        if mode not in ('all','demo','live') or days not in (7,30,90):handler.send({'error':'Invalid filter'},400)
        else:handler.send(ledger.metrics(mode,days))
    elif path=='/api/admin/settings':handler.send({'settings':ledger.settings(),'services':status()})
    else:handler.send({'error':'Not found'},404)
    return True


def post(handler,path,body):
    if not path.startswith(('/api/agent/','/api/admin/')):return False
    if path=='/api/admin/login':
        token=os.getenv('UPNEXT_ADMIN_TOKEN','');provided=body.get('token','')
        if not token or not isinstance(provided,str) or not hmac.compare_digest(token,provided):
            handler.send({'error':'Invalid admin token'},401);return True
        sid=secrets.token_urlsafe(32);SESSIONS[sid]=time.time()+8*3600
        handler.send_response(200);handler.send_header('Content-Type','application/json');handler.send_header('Cache-Control','no-store');handler.send_header('Set-Cookie',f'upnext_admin={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800');handler.end_headers();handler.wfile.write(b'{"ok":true}');return True
    if path.startswith('/api/admin/') and not admin_allowed(handler):handler.send({'error':'Admin sign-in required'},401);return True
    try:
        if path=='/api/agent/runs':
            prompt=body.get('message');mode=body.get('mode','demo');cid=body.get('conversation_id');event_id=body.get('event_id')
            if not isinstance(prompt,str) or not 1<=len(prompt.strip())<=4000 or mode not in ('demo','live'):raise ValueError('Enter a message of 1–4000 characters and a valid mode.')
            if cid is not None and (not isinstance(cid,str) or len(cid)>50):raise ValueError('Invalid conversation')
            if event_id is not None and (not isinstance(event_id,str) or len(event_id)!=64):raise ValueError('Invalid calendar event')
            run=submit(prompt,mode,cid,event_id=event_id);handler.send({'id':run['id'],'conversation_id':run['conversation_id']},202)
        elif path=='/api/agent/preferences':
            if set(body)-{'preferences','budget_cents'}:raise ValueError('Only shopping preferences and budget can be updated here.')
            saved=ledger.set_settings(body);handler.send({'preferences':saved['preferences'],'budget_cents':saved['budget_cents']})
        elif path=='/api/agent/feedback':
            run=ledger.feedback(body.get('run_id'),body.get('value'));tenancy.enqueue(POOL,agent.flush_events);handler.send({'feedback':run['feedback']})
        elif path=='/api/admin/settings':handler.send({'settings':ledger.set_settings(body)})
        elif path=='/api/admin/scan':
            tenancy.enqueue(POOL,scan);handler.send({'queued':True},202)
        elif path=='/api/admin/telemetry/retry':
            tenancy.enqueue(POOL,agent.flush_events);handler.send({'queued':True},202)
        else:handler.send({'error':'Not found'},404)
    except (ValueError,TypeError) as exc:handler.send({'error':str(exc)},400)
    return True
