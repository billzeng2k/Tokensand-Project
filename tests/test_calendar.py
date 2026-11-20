from datetime import date
import json
import pytest
from tokensand import calendar
from tokensand.storage import MemoryStore
from tokensand.tools import FixtureTools
from tokensand.workflow import run


def event(id='a', calendar_id='one', **changes):
    return dict({'id':id,'calendar_id':calendar_id,'summary':'Dinner','start':{'date':'2026-12-04'},'status':'confirmed','updated':'2026-11-20T00:00:00Z'}, **changes)


def test_calendar_identity_and_filtering():
    rows=[event(),event(calendar_id='two'),event(id='cancel',status='cancelled'),event(id='recurring',recurrence=['RRULE:FREQ=WEEKLY']),event(id='old',start={'date':'2020-01-01'})]
    result=calendar.view({'records':rows,'synced_at':'now'},today=date(2026,11,20))
    assert len(result['events'])==2
    assert result['events'][0]['id']!=result['events'][1]['id']
    assert result['events'][0]['source']=='airbyte-google-calendar'


def test_timezone_date_preserved():
    assert calendar.normalize(event(start={'dateTime':'2026-12-04T23:30:00-08:00'}),'now')['date']=='2026-12-04'


def test_sync_atomic_and_events_only(tmp_path,monkeypatch):
    monkeypatch.setattr(calendar,'CONFIG',tmp_path/'config.json');monkeypatch.setattr(calendar,'SNAPSHOT',tmp_path/'snapshot.json')
    calendar.private_json(calendar.CONFIG,{'calendarid':'primary'})
    catalog={'catalog':{'streams':[{'name':'events','json_schema':{'type':'object'}},{'name':'acl'}]}}
    def connector(command, files):
        if command=='discover':return [catalog]
        assert [s['stream']['name'] for s in files['catalog']['streams']]==['events']
        return [{'record':{'stream':'events','data':event()}},{'trace':{'stream_status':{'status':'COMPLETE'}}}]
    monkeypatch.setattr(calendar,'connector',connector)
    calendar.sync();saved=calendar.SNAPSHOT.read_bytes()
    monkeypatch.setattr(calendar,'connector',lambda command,files:[catalog] if command=='discover' else [{'record':{'stream':'events','data':event(id='partial')}}])
    with pytest.raises(RuntimeError):calendar.sync()
    assert calendar.SNAPSHOT.read_bytes()==saved


def test_removed_event_cannot_create_task(monkeypatch):
    monkeypatch.setattr(calendar,'sync',lambda:{'events':[],'synced_at':'now'})
    store=MemoryStore();tools=FixtureTools(store=store)
    tools.data['event']=calendar.selected_event('removed')
    report=run(tools,store,tools.data['memory'],tools.data['profile'],'removed')
    assert report['status']=='event_cancelled'
    assert not store.tasks


def test_real_event_identity_enters_audit_and_repeats_once():
    store=MemoryStore();tools=FixtureTools(store=store)
    e=calendar.normalize(event(),'now');tools.data['event']=e
    report=run(tools,store,tools.data['memory'],tools.data['profile'],e['id'])
    assert report['status']=='task_saved'
    assert report['steps'][0]['result']['calendar_id']=='one'
    repeated=run(tools,store,tools.data['memory'],tools.data['profile'],e['id'])
    assert repeated['status']=='already_saved'
    assert len(store.tasks)==1
