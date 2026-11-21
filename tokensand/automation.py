"""Per-account daily scheduling, persisted across server restarts."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json
import re
import threading
from . import observability as ledger, tenancy, auth

SYNC_QUEUED=set()
SYNC_LOCK=threading.Lock()

DEFAULT = {'enabled':False,'time':'09:00','timezone':'America/Los_Angeles','lookahead_days':30}

def settings():
    with ledger.db() as c:
        row=c.execute('SELECT payload FROM settings WHERE id=3').fetchone()
    return {**DEFAULT, **(json.loads(row[0]) if row else {})}

def save(values):
    if set(values)-set(DEFAULT):raise ValueError('Unknown automation setting')
    result={**settings(),**values}
    if type(result['enabled']) is not bool:raise ValueError('Invalid enabled setting')
    if not isinstance(result['time'],str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',result['time']):raise ValueError('Choose a valid daily time')
    try:ZoneInfo(result['timezone'])
    except (ZoneInfoNotFoundError,TypeError,ValueError):raise ValueError('Choose a valid IANA timezone')
    if type(result['lookahead_days']) is not int or result['lookahead_days']<1:raise ValueError('Look ahead must be a positive whole number of days')
    with ledger.db() as c:c.execute('INSERT OR REPLACE INTO settings VALUES(3,?)',(json.dumps(result),))
    return result

def status():
    with ledger.db() as c:
        row=c.execute("SELECT payload FROM scans WHERE json_extract(payload,'$.kind') IN ('daily','calendar_sync') ORDER BY created_at DESC LIMIT 1").fetchone()
    return {'settings':settings(),'last_run':json.loads(row[0]) if row else None,'research_queued':tenancy.USER.get() in SYNC_QUEUED}

def occasion(e):
    return e.get('title','').strip().casefold() != 'sleep'


def covered(event_id):
    with ledger.db() as c:rows=c.execute('SELECT payload FROM runs').fetchall()
    for row in rows:
        r=json.loads(row[0])
        if r.get('event_id')!=event_id:continue
        if r['status'] in ('queued','running'):return True
        if r['mode']=='live' and r['status']=='no_action':return True
        if r['mode']=='live' and r['status']=='completed' and (r.get('result',{}).get('items') or any(g.get('items') for g in r.get('result',{}).get('groups',[]))):return True
    return False

def run(snapshot=None):
    from .calendar import sync
    from . import agent
    scheduled=snapshot is None
    result={'kind':'daily' if scheduled else 'calendar_sync','status':'completed','runs_created':0,'skipped':0,'run_ids':[]}
    try:
        cfg=settings()
        if (scheduled and not cfg['enabled']) or not auth.connected(tenancy.USER.get()) or not ledger.settings()['agent_enabled']:return
        today=datetime.now(ZoneInfo(cfg['timezone'])).date()
        snapshot=sync() if scheduled else snapshot # Failure stops the run; never research from stale data.
        for event in snapshot['events']:
            if scheduled and not settings()['enabled']:break
            if not 0<=(datetime.fromisoformat(event['date']).date()-today).days<=cfg['lookahead_days'] or not occasion(event):continue
            if covered(event['id']):result['skipped']+=1;continue
            item=ledger.create_run('Review this upcoming event and recommend Amazon products only for a concrete need. Consider owned items and preferences first.', 'live', trigger='daily' if scheduled else 'calendar_sync',event_id=event['id'])
            result['run_ids'].append(item['id']);result['runs_created']+=1
            agent.execute(item['id'])
            finished=ledger.get(item['id'])
            if finished['status'] in ('failed','blocked','interrupted'):
                result['status']='partial';result['error_code']=finished.get('error_code','research_failed');break
    except Exception as exc:
        result.update(status='failed',error_code=agent.error_code(exc))
    ledger.record_scan(result)

def tick(pool,now=None):
    now=now or datetime.now(timezone.utc)
    for user in auth.users():
        with tenancy.scope(user['id']):
            cfg=settings();local=now.astimezone(ZoneInfo(cfg['timezone']))
            if not cfg['enabled'] or local.strftime('%H:%M')<cfg['time'] or not auth.connected(user['id']):continue
            # Atomic daily claim prevents duplicate queuing, including after restart/DST.
            key='daily:'+local.date().isoformat()
            if ledger.reserve_trigger(key):tenancy.enqueue(pool,run)


def after_sync(snapshot):
    """Only explicit app syncs enqueue this; internal evidence refreshes never recurse."""
    from .agent_api import POOL
    uid=tenancy.USER.get()
    if not uid:return False
    with SYNC_LOCK:
        if uid in SYNC_QUEUED:return False
        SYNC_QUEUED.add(uid)
    def work():
        try:run(snapshot)
        finally:
            with SYNC_LOCK:SYNC_QUEUED.discard(uid)
    try:tenancy.enqueue(POOL,work)
    except Exception:
        with SYNC_LOCK:SYNC_QUEUED.discard(uid)
        raise
    return True
