"""Durable local run ledger. Payloads stay local; telemetry is an explicit allowlist."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
import math
import os
import re
import sqlite3
import uuid
from .config import LOCAL
from . import tenancy

DB = LOCAL / 'agent-traces.sqlite3'
DEFAULTS = {'agent_enabled':True,'web_enabled':True,'proactive_enabled':False,
            'proactive_mode':'demo','interval_minutes':60,'lookahead_days':14,'max_daily_runs':5,
            'budget_cents':8000,'preferences':'Prefer cotton; avoid itchy wool. Own a navy jacket.',
            'strategy':'evidence_first','memory_backend':'profile','mirror_singlestore':False}
TERMINAL = {'completed','no_action','failed','blocked','interrupted'}
SECRET = re.compile(r'(?:sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._-]{12,}|(?i:api[_ -]?key|password|refresh_token|client_secret)\s*[:=]\s*[^\s,;]+)')


def clean(value):
    if isinstance(value,str): return SECRET.sub('[REDACTED]',value)
    if isinstance(value,list): return [clean(v) for v in value]
    if isinstance(value,dict): return {k:('[REDACTED]' if k.lower() in {'authorization','api_key','password','refresh_token','client_secret','access_token'} else clean(v)) for k,v in value.items()}
    return value


def now(): return datetime.now(timezone.utc).isoformat()


@contextmanager
def db():
    path = tenancy.directory() / 'agent-traces.sqlite3' if tenancy.USER.get() else DB
    path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(path,timeout=15);conn.row_factory=sqlite3.Row
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, title TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, created_at TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS runs_conversation ON runs(conversation_id,created_at);
    CREATE INDEX IF NOT EXISTS runs_created ON runs(created_at);
    CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, run_id TEXT, payload TEXT NOT NULL, delivered INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0, error TEXT);
    CREATE TABLE IF NOT EXISTS triggers(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, run_id TEXT);
    CREATE TABLE IF NOT EXISTS review_tasks(id TEXT PRIMARY KEY, run_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS item_decisions(event_id TEXT NOT NULL,item_key TEXT NOT NULL,updated_at TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(event_id,item_key));
    CREATE TABLE IF NOT EXISTS preference_notes(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,text TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS scans(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
    ''')
    os.chmod(path,0o600)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback();raise
    finally:conn.close()


def analytics_id():
    with db() as c:
        c.execute('INSERT OR IGNORE INTO settings VALUES(2,?)',(json.dumps(str(uuid.uuid4())),))
        return json.loads(c.execute('SELECT payload FROM settings WHERE id=2').fetchone()[0])


def settings():
    with db() as c:r=c.execute('SELECT payload FROM settings WHERE id=1').fetchone()
    defaults = {**DEFAULTS, 'preferences': ''} if tenancy.USER.get() else DEFAULTS
    return {**defaults,**(json.loads(r[0]) if r else {})}


def set_settings(values):
    current=settings()
    if set(values)-set(DEFAULTS):raise ValueError('Unknown setting')
    for key,value in values.items():
        expected=type(DEFAULTS[key])
        if type(value) is not expected:raise ValueError(f'Invalid {key}')
    if tenancy.USER.get() and (values.get('memory_backend') == 'cognee' or values.get('mirror_singlestore')):
        raise ValueError('Shared legacy memory and trace mirroring are disabled for accounts')
    current.update(values)
    for key,low,high in [('interval_minutes',5,1440),('lookahead_days',1,90),('max_daily_runs',1,20),('budget_cents',100,1000000)]:
        if not low<=current[key]<=high:raise ValueError(f'Invalid {key}')
    if current['proactive_mode'] not in ('demo','live') or current['strategy'] not in ('evidence_first','budget_first') or current['memory_backend'] not in ('profile','cognee'):raise ValueError('Invalid option')
    if len(current['preferences'])>2000:raise ValueError('Preferences too long')
    with db() as c:c.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',(json.dumps(clean(current)),))
    return current


def create_run(prompt,mode,conversation_id=None,trigger='manual',event_id=None):
    run_id=str(uuid.uuid4());stamp=now()
    with db() as c:
        if conversation_id:
            if not c.execute('SELECT 1 FROM conversations WHERE id=?',(conversation_id,)).fetchone():raise ValueError('Conversation not found')
            if c.execute("SELECT 1 FROM runs WHERE conversation_id=? AND status IN ('queued','running')",(conversation_id,)).fetchone():raise ValueError('This conversation already has an active run')
            linked=c.execute('SELECT payload FROM runs WHERE conversation_id=? LIMIT 1',(conversation_id,)).fetchone()
            if linked and json.loads(linked[0]).get('event_id')!=event_id:raise ValueError('Conversation belongs to a different event')
        else:
            conversation_id=str(uuid.uuid4())
            c.execute('INSERT INTO conversations VALUES(?,?,?)',(conversation_id,stamp,clean(prompt[:90])))
        run={'id':run_id,'conversation_id':conversation_id,'created_at':stamp,'mode':mode,'status':'queued','trigger':trigger,'event_id':event_id,
             'prompt_version':'upnext-research-v1','messages':[{'role':'user','content':clean(prompt),'at':stamp}],
             'spans':[],'usage':{'input_tokens':0,'output_tokens':0},'model_calls':0,'cost_estimate_usd':0 if mode=='demo' else None,
             'result':None,'feedback':None,'telemetry':{'state':'pending'}}
        c.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',(run_id,conversation_id,stamp,mode,'queued',json.dumps(run)))
    return run


def save(run):
    with db() as c:
        existing=c.execute('SELECT payload FROM runs WHERE id=?',(run['id'],)).fetchone()
        if existing and json.loads(existing[0]).get('feedback'):run['feedback']=json.loads(existing[0])['feedback']
        c.execute('UPDATE runs SET status=?,payload=? WHERE id=?',(run['status'],json.dumps(clean(run)),run['id']))


def get(run_id):
    with db() as c:r=c.execute('SELECT payload FROM runs WHERE id=?',(run_id,)).fetchone()
    return json.loads(r[0]) if r else None


def conversations():
    with db() as c:rows=c.execute('SELECT * FROM conversations ORDER BY created_at DESC LIMIT 100').fetchall()
    return [dict(r) for r in rows]


def conversation(cid):
    with db() as c:rows=c.execute('SELECT payload FROM runs WHERE conversation_id=? ORDER BY created_at,id',(cid,)).fetchall()
    return [json.loads(r[0]) for r in rows]


def query(mode='all',days=30):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    with db() as c:
        rows=c.execute('SELECT payload FROM runs WHERE created_at>=? AND (?=\'all\' OR mode=?) ORDER BY created_at DESC',(cutoff,mode,mode)).fetchall()
    return [json.loads(r[0]) for r in rows]


def queue_event(run,event_type,properties=None,event_id=None):
    props={k:run.get(k) for k in ['conversation_id','mode','trigger','status','prompt_version','model']}
    props.update({'run_id':run['id'],'strategy':run.get('flags',{}).get('strategy'),'schema_version':1})
    props.update(properties or {})
    allowed={'conversation_id','mode','trigger','status','prompt_version','model','run_id','strategy','schema_version','latency_ms','input_tokens','output_tokens','model_calls','source_count','item_count','cost_estimate_usd','feedback','span_kind','call_status','error_code','category_count','recipe_count','missing_rating_count','missing_price_count','retrieval_attempts','retrieval_successes','item_action'}
    payload={'event_type':event_type,'user_id':analytics_id(),'insert_id':event_id or str(uuid.uuid4()),'time':int(datetime.now(timezone.utc).timestamp()*1000),'event_properties':{k:v for k,v in props.items() if k in allowed and v is not None}}
    with db() as c:c.execute('INSERT OR IGNORE INTO outbox(id,run_id,payload) VALUES(?,?,?)',(payload['insert_id'],run['id'],json.dumps(payload)))


def pending_events():
    with db() as c:rows=c.execute('SELECT id,run_id,payload FROM outbox WHERE delivered=0 ORDER BY rowid LIMIT 100').fetchall()
    return [dict(r)|{'payload':json.loads(r['payload'])} for r in rows]


def delivery(ids,error=None):
    with db() as c:c.executemany('UPDATE outbox SET delivered=?,attempts=attempts+1,error=? WHERE id=?',[(0 if error else 1,error,i) for i in ids])


def save_task(run):
    task={'id':run['id'],'run_id':run['id'],'conversation_id':run['conversation_id'],'state':'needs_user_review','created_at':now(),'mode':run['mode'],'recommendation':run['result'],'order_placed':False}
    with db() as c:c.execute('INSERT OR IGNORE INTO review_tasks VALUES(?,?,?)',(task['id'],run['id'],json.dumps(clean(task))))
    return task['id']


def feedback(run_id,value):
    if value not in ('helpful','not_helpful','dismissed'):raise ValueError('Invalid feedback')
    with db() as c:
        row=c.execute('SELECT payload FROM runs WHERE id=?',(run_id,)).fetchone()
        if not row:raise ValueError('Run not found')
        run=json.loads(row[0])
        if run['status'] not in ('completed','no_action'):raise ValueError('Run has no recommendation to review')
        if run.get('feedback') is not None:return run
        run['feedback']={'value':value,'at':now()}
        c.execute('UPDATE runs SET payload=? WHERE id=?',(json.dumps(run),run_id))
    queue_event(run,'Recommendation Feedback',{'feedback':value},f'{run_id}:feedback')
    return run


def reserve_trigger(key):
    with db() as c:
        result=c.execute('INSERT OR IGNORE INTO triggers(id,created_at) VALUES(?,?)',(key,now()))
        return bool(result.rowcount)


def record_scan(value):
    value={'id':str(uuid.uuid4()),'created_at':now(),**value}
    with db() as c:c.execute('INSERT INTO scans VALUES(?,?,?)',(value['id'],value['created_at'],json.dumps(value)))
    return value


def recover():
    with db() as c:rows=c.execute("SELECT payload FROM runs WHERE status IN ('queued','running')").fetchall()
    for row in rows:
        run=json.loads(row[0]);run.update(status='interrupted',finished_at=now(),error_code='server_restarted');save(run)


def percentile(values,p):return sorted(values)[max(0,math.ceil(len(values)*p)-1)] if values else None


def metrics(mode='all',days=30):
    runs=query(mode,days);terminal=[r for r in runs if r['status'] in TERMINAL]
    completed=[r for r in terminal if r['status']=='completed'];evaluated=[r for r in terminal if r['status'] in ('completed','no_action')]
    rated=[r for r in evaluated if r.get('feedback') and r['feedback']['value'] in ('helpful','not_helpful')]
    spans=[s for r in runs for s in r['spans']];calls=[s for s in spans if s['kind']=='model']
    items=[i for r in evaluated for i in (r.get('result') or {}).get('items',[])]
    known_cost=[r['cost_estimate_usd'] for r in terminal if r.get('cost_estimate_usd') is not None]
    latency=[r['latency_ms'] for r in terminal if r.get('latency_ms') is not None]
    with db() as c:
        pending=c.execute('SELECT COUNT(*) FROM outbox WHERE delivered=0').fetchone()[0]
        scans=[json.loads(r[0]) for r in c.execute('SELECT payload FROM scans ORDER BY created_at DESC LIMIT 20')]
    statuses={s:sum(r['status']==s for r in runs) for s in ('queued','running','completed','no_action','failed','blocked','interrupted')}
    return {'window_days':days,'mode':mode,'runs':len(runs),'terminal_runs':len(terminal),'statuses':statuses,
            'completion_rate':len(evaluated)/len(terminal) if terminal else None,
            'recommendation_rate':len(completed)/len(evaluated) if evaluated else None,
            'helpful_rate':sum(r['feedback']['value']=='helpful' for r in rated)/len(rated) if rated else None,'rated_runs':len(rated),
            'feedback_count':sum(bool(r.get('feedback')) for r in evaluated),
            'p50_latency_ms':percentile(latency,.5),'p95_latency_ms':percentile(latency,.95),
            'model_calls':len(calls),'model_errors':sum(s['status']=='failed' for s in calls),
            'model_p95_latency_ms':percentile([s['duration_ms'] for s in calls if s.get('duration_ms') is not None],.95),
            'input_tokens':sum(r['usage']['input_tokens'] for r in runs),'output_tokens':sum(r['usage']['output_tokens'] for r in runs),
            'estimated_cost_usd':sum(known_cost) if known_cost else None,'cost_coverage':len(known_cost)/len(terminal) if terminal else None,
            'priced_items':sum(i.get('price_cents') is not None for i in items),'rated_items':sum(i.get('rating') is not None for i in items),'recipe_count':sum(len((r.get('result') or {}).get('recipes',[])) for r in evaluated),'item_count':len(items),'source_linked_items':sum(bool(i.get('source_url')) for i in items),
            'unverified_items':sum(bool(i.get('uncertainties')) for i in items),
            'pending_telemetry_events':pending,'recent_scans':scans,
            'recent_runs':[{k:r.get(k) for k in ('id','conversation_id','created_at','status','mode','trigger','latency_ms','model','feedback','cost_estimate_usd')} for r in runs[:100]]}
