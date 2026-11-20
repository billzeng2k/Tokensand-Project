from datetime import datetime, timezone
import pytest
from tokensand import automation as a, observability as ledger, tenancy

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(tenancy,'LOCAL',tmp_path)
    monkeypatch.setattr(ledger,'DB',tmp_path/'ledger.db')
    monkeypatch.setattr(a.auth,'users',lambda:[{'id':'a'*64}])
    monkeypatch.setattr(a.auth,'connected',lambda uid:True)
    with tenancy.scope('a'*64):yield

def test_validation_and_isolation(isolated):
    a.save({'enabled':True,'time':'09:30'})
    with pytest.raises(ValueError):a.save({'lookahead_days':31})
    with pytest.raises(ValueError):a.save({'time':'24:00'})
    with pytest.raises(ValueError):a.save({'timezone':'bad/timezone'})
    with tenancy.scope('b'*64):assert not a.settings()['enabled']
    assert a.settings()['time']=='09:30'

def test_daily_claim_restart_and_timezone(isolated,monkeypatch):
    queued=[]
    monkeypatch.setattr(tenancy,'enqueue',lambda pool,fn:queued.append(tenancy.USER.get()))
    a.save({'enabled':True})
    a.tick(None,datetime(2026,11,21,16,59,tzinfo=timezone.utc))
    assert not queued
    a.tick(None,datetime(2026,11,21,17,tzinfo=timezone.utc))
    a.tick(None,datetime(2026,11,21,23,tzinfo=timezone.utc))
    assert queued==['a'*64]
    a.tick(None,datetime(2026,11,22,17,tzinfo=timezone.utc))
    assert len(queued)==2

def test_run_skips_covered_routine_and_distant(isolated,monkeypatch):
    from tokensand import calendar,agent
    a.save({'enabled':True})
    today=datetime.now(a.ZoneInfo('America/Los_Angeles')).date()
    events=[{'id':str(i)*64,'date':str(today),'title':title} for i,title in enumerate(['Potluck','Sleep','Birthday','Party'])]
    events.append({'id':'4'*64,'date':str(today+a.timedelta(days=31)),'title':'Birthday'})
    monkeypatch.setattr(calendar,'sync',lambda:{'events':events})
    # Existing live recommendations suppress research; old demo data does not.
    run=ledger.create_run('test','live',event_id='0'*64)
    with ledger.db() as c:
        import json
        run.update(status='completed',result={'groups':[{'items':[{'name':'gift'}]}]})
        c.execute('UPDATE runs SET status=?,payload=? WHERE id=?',('completed',json.dumps(run),run['id']))
    ledger.create_run('queued','live',event_id='2'*64)
    executed=[]
    monkeypatch.setattr(agent,'execute',lambda rid:executed.append(rid))
    a.run()
    assert len(executed)==1
    assert ledger.get(executed[0])['event_id']=='3'*64
    assert a.status()['last_run']['skipped']==2

def test_sync_runs_even_with_schedule_disabled(isolated,monkeypatch):
    from tokensand import agent,calendar
    monkeypatch.setattr(calendar,'sync',lambda:pytest.fail('Snapshot must be reused'))
    executed=[]
    monkeypatch.setattr(agent,'execute',lambda rid:executed.append(rid))
    a.run({'events':[{'id':'5'*64,'date':str(datetime.now(a.ZoneInfo('America/Los_Angeles')).date()),'title':'Birthday'}]})
    assert len(executed)==1
    assert ledger.get(executed[0])['trigger']=='calendar_sync'

def test_sync_queue_coalesces_and_preserves_account(isolated,monkeypatch):
    queued=[]
    monkeypatch.setattr(tenancy,'enqueue',lambda pool,fn:queued.append(fn))
    monkeypatch.setattr(a,'run',lambda snapshot:None)
    assert a.after_sync({'events':[]})
    assert not a.after_sync({'events':[]})
    assert len(queued)==1
    queued[0]()
    assert 'a'*64 not in a.SYNC_QUEUED
