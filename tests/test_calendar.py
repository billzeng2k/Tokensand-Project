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
    singles=[e for e in result['events'] if not e['recurring']]
    assert len(singles)==2
    assert any(e['recurring'] for e in result['events'])
    assert singles[0]['id']!=singles[1]['id']
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


def test_yearly_birthday_and_title_categories():
    rows=[event(id='birthday',eventType='birthday',summary='Person',start={'date':'1990-12-04'},end={'date':'1990-12-05'},recurrence=['RRULE:FREQ=YEARLY']),event(id='holiday',summary='Christmas party'),event(id='title',summary="Friend’s birthday")]
    result=calendar.view({'records':rows,'synced_at':'now'},today=date(2026,11,20))
    birthday=next(e for e in result['events'] if e['google_event_id']=='birthday')
    assert birthday['date']=='2026-12-04' and birthday['kind']=='birthday' and birthday['recurring']
    assert birthday['kind_source']=='Google birthday event'
    assert next(e for e in result['events'] if e['google_event_id']=='holiday')['kind']=='holiday'
    assert next(e for e in result['events'] if e['google_event_id']=='title')['kind_source']=='Suggested from event title'


def test_recurrence_exclusions_moved_and_cancelled_instances():
    parent=event(id='weekly',start={'date':'2026-12-01'},end={'date':'2026-12-02'},recurrence=['RRULE:FREQ=WEEKLY;COUNT=4','EXDATE;VALUE=DATE:20261222'])
    cancelled=event(id='cancel',recurringEventId='weekly',originalStartTime={'date':'2026-12-08'},status='cancelled')
    moved=event(id='moved',recurringEventId='weekly',originalStartTime={'date':'2026-12-15'},start={'date':'2026-12-16'},end={'date':'2026-12-17'})
    result=calendar.view({'records':[parent,cancelled,moved],'synced_at':'now'},today=date(2026,11,20))
    assert [e['date'] for e in result['events']]==['2026-12-01','2026-12-16']
    original=calendar.view({'records':[parent],'synced_at':'earlier'},today=date(2026,11,20))
    assert next(e for e in original['events'] if e['date']=='2026-12-15')['id']==result['events'][1]['id']


def test_weekly_recurrence_preserves_dst_and_hides_cancelled_series():
    parent=event(id='weekly',start={'dateTime':'2026-10-25T09:00:00-07:00','timeZone':'America/Los_Angeles'},end={'dateTime':'2026-10-25T10:00:00-07:00','timeZone':'America/Los_Angeles'},recurrence=['RRULE:FREQ=WEEKLY;COUNT=2'])
    result=calendar.view({'records':[parent],'synced_at':'now'},today=date(2026,10,25))
    assert [e['start']['dateTime'] for e in result['events']]==['2026-10-25T09:00:00-07:00','2026-11-01T09:00:00-08:00']
    parent['status']='cancelled'
    exception=event(id='exception',recurringEventId='weekly',originalStartTime={'dateTime':'2026-11-01T09:00:00-08:00'})
    assert calendar.view({'records':[parent,exception],'synced_at':'now'},today=date(2026,10,25))['events']==[]


def test_ongoing_multiday_event_and_bad_recurrence():
    rows=[event(start={'date':'2026-11-19'},end={'date':'2026-11-22'}),event(id='bad',recurrence=['RRULE:FREQ=SECONDLY'])]
    result=calendar.view({'records':rows,'synced_at':'now'},today=date(2026,11,20))
    assert len(result['events'])==1 and result['warnings']
    assert result['window_end']=='2027-11-20'


def test_same_day_recurring_event_without_end():
    row=event(start={'date':'2020-11-20'},recurrence=['RRULE:FREQ=YEARLY'])
    result=calendar.view({'records':[row],'synced_at':'now'},today=date(2026,11,20))
    assert result['events'][0]['date']=='2026-11-20'

def test_calendar_description_preserved_and_bounded():
    description='Festive dress code. Bring a vegetarian side; plates supplied.'
    result=calendar.view({'records':[event(description=description)],'synced_at':'now'},today=date(2026,11,20))
    assert result['events'][0]['description']==description
    assert calendar.normalize(event(description=None),'now')['description']==''
    assert len(calendar.normalize(event(description='x'*7000),'now')['description'])==6000
