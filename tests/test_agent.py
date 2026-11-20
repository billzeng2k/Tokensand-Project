import json
from datetime import date,timedelta
import pytest
from tokensand import agent,observability as ledger,agent_api

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(ledger,'DB',tmp_path/'traces.db')
    def sdk(payload):
        if payload['action']=='evaluate':
            controls=payload['controls']
            return {'mode':'offline-overrides','strategy':controls['strategy'],'gates':{k:{'value':controls[k]} for k in ('agent_enabled','web_enabled','proactive_enabled')}}
        return {'mode':'local-file-transport','count':len(payload['events'])}
    monkeypatch.setattr(agent,'sdk',sdk)
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)


def run(prompt='Find a jacket for dinner',mode='demo',cid=None):return agent.execute(ledger.create_run(prompt,mode,cid)['id'])


def test_demo_trace_persistence_followup_and_feedback():
    a=run();b=run('I already own a suitable jacket',cid=a['conversation_id'])
    assert a['status']=='completed' and a['task_id']
    assert b['status']=='no_action' and not b.get('task_id')
    assert a['model_calls']==0 and a['cost_estimate_usd']==0
    assert len(ledger.conversation(a['conversation_id']))==2
    ledger.feedback(a['id'],'helpful');ledger.feedback(a['id'],'not_helpful')
    assert ledger.get(a['id'])['feedback']['value']=='helpful'
    m=ledger.metrics();assert m['helpful_rate']==1 and m['completion_rate']==1 and m['rated_runs']==1
    assert m['model_calls']==0


def test_disabled_gate_prevents_recommendation():
    ledger.set_settings({'agent_enabled':False})
    r=run();assert r['status']=='blocked' and r['error_code']=='agent_disabled'
    assert not r.get('task_id')


def test_live_without_key_does_not_fall_back_to_demo():
    r=run(mode='live');assert r['status']=='blocked' and r['error_code']=='missing_openai_key'
    assert r['cost_estimate_usd'] is None and r['result'] is None


def test_failed_runs_remain_in_denominator_and_unknown_not_zero():
    run();run('simulate failure');run(mode='live')
    m=ledger.metrics();assert m['completion_rate']==pytest.approx(1/3)
    assert m['statuses']['failed']==1 and m['statuses']['blocked']==1
    assert m['cost_coverage']==pytest.approx(2/3)
    assert ledger.metrics('live')['estimated_cost_usd'] is None


def test_sources_and_budget_enforced():
    result,sources=agent.demo_result('jacket',{},'evidence_first')
    assert not agent.validate_result(result,sources,100,'demo')['items']
    result['groups'][0]['items'][0]['source_url']='https://evil.example/forged'
    assert not agent.validate_result(result,sources,8000,'demo')['items']
    assert not agent.safe_url('javascript:alert(1)')
    assert not agent.safe_url('https://127.0.0.1/private')
    assert not agent.safe_url('https://example.com@localhost/private')


def test_redaction_and_telemetry_allowlist():
    r=run('password=secret123 Find a jacket')
    assert 'secret123' not in json.dumps(ledger.get(r['id']))
    ledger.queue_event(r,'Test',{'prompt':'private','calendar_title':'private','latency_ms':12})
    e=ledger.pending_events()[0]['payload']
    assert 'prompt' not in e['event_properties'] and 'calendar_title' not in e['event_properties']
    assert e['event_properties']['latency_ms']==12


def test_telemetry_failure_does_not_lose_result(monkeypatch):
    base=agent.sdk
    def sdk(p):
        if p['action']=='events':raise RuntimeError('offline')
        return base(p)
    monkeypatch.setattr(agent,'sdk',sdk)
    r=run();assert r['status']=='completed' and r['telemetry']['state']=='pending'
    ids=[e['id'] for e in ledger.pending_events()];assert len(ids)==2
    monkeypatch.setattr(agent,'sdk',base);agent.flush_events()
    assert not ledger.pending_events()
    with ledger.db() as c:assert [r[0] for r in c.execute('SELECT id FROM outbox ORDER BY rowid')]==ids


def test_recovery_marks_interrupted():
    r=ledger.create_run('hello','demo');ledger.recover()
    assert ledger.get(r['id'])['status']=='interrupted'


def test_calendar_scan_deduplicates_and_caps(monkeypatch):
    from tokensand import calendar
    ledger.set_settings({'proactive_enabled':True,'max_daily_runs':1})
    e={'id':'a'*64,'title':'Dinner','date':(date.today()+timedelta(days=2)).isoformat(),'updated':'v1','status':'confirmed','source':'test','synced_at':'now'}
    monkeypatch.setattr(calendar,'sync',lambda:{'events':[e]})
    monkeypatch.setattr(calendar,'selected_event',lambda id:e)
    a=agent_api.scan();assert a['runs_created']==1
    ledger.set_settings({'max_daily_runs':5})
    b=agent_api.scan();assert b['runs_created']==0 and b['duplicate_suppressed']==1


def test_calendar_failure_is_visible(monkeypatch):
    from tokensand import calendar
    ledger.set_settings({'proactive_enabled':True})
    def fail():raise RuntimeError('calendar unavailable')
    monkeypatch.setattr(calendar,'sync',fail)
    assert agent_api.scan()['status']=='failed'
    assert not ledger.query()


def test_live_request_contract_citations_usage_and_no_hidden_reasoning(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    result,sources=agent.demo_result('jacket',{},'evidence_first')
    sources[0]['url']='https://www.amazon.com/dp/B000TEST01'
    result['groups'][0]['items'][0]['source_url']=sources[0]['url']
    calls=[]
    responses=[{'id':'response1','status':'completed','usage':{'input_tokens':100,'output_tokens':50},'output':[
        {'type':'reasoning','content':'HIDDEN_THOUGHTS'},
        {'type':'web_search_call','id':'web1','status':'completed','action':{'type':'search','sources':sources}},
        {'type':'message','content':[{'type':'output_text','text':'A jacket with a source','annotations':[]}]}]},
        {'id':'response2','status':'completed','usage':{'input_tokens':200,'output_tokens':100},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(result)}]}]}]
    class Response:
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps(self.data).encode()
    def request(req,timeout):
        calls.append(json.loads(req.data));return Response(responses.pop(0))
    monkeypatch.setattr(agent.urllib.request,'urlopen',request)
    r=run(mode='live');assert r['status']=='completed' and r['model_calls']==2
    assert r['usage']=={'input_tokens':300,'output_tokens':150}
    assert all(c['store'] is False for c in calls)
    assert calls[0]['tools'][0]['type']=='web_search'
    assert calls[1]['text']['format']['type']=='json_schema'
    assert 'HIDDEN_THOUGHTS' not in json.dumps(r)
    assert r['cost_estimate_usd'] is None


def test_settings_validation_and_percentile():
    with pytest.raises(ValueError):ledger.set_settings({'interval_minutes':0})
    with pytest.raises(ValueError):ledger.set_settings({'agent_enabled':'yes'})
    assert ledger.percentile([100,200,500],.95)==500


def test_narrower_user_budget_and_followup_are_preserved():
    a=run('Find a jacket under $30')
    b=run('Show another option',cid=a['conversation_id'])
    assert a['context']['budget_cents']==3000 and b['context']['budget_cents']==3000
    assert a['status']=='no_action' and b['status']=='no_action'


def test_analytics_identity_stable_and_not_shared_constant():
    first=ledger.analytics_id();assert first==ledger.analytics_id()
    assert first!='upnext-local-user' and len(first)==36


def test_christmas_plan_grouped_and_recipe_ideas():
    r=run('Hosting a Christmas party with each item under $80')
    assert r['status']=='completed'
    assert [len(g['items']) for g in r['result']['groups']]==[2,3]
    assert len(r['result']['recipes'])==2
    assert all('rating' in i and 'review_count' in i for i in r['result']['items'])
    assert all(x['type']=='generated_recipe_idea' for x in r['result']['recipes'])


def test_live_rejects_non_amazon_and_search_pages_and_invalid_ratings():
    result,sources=agent.demo_result('jacket',{},'evidence_first')
    assert not agent.validate_result(result,sources,8000)['items']
    for url in ['https://www.amazon.com/s?k=coat','https://amazon.com.attacker.example/dp/B000TEST01']:
        assert not agent.amazon_product(url)
    assert agent.amazon_product('https://www.amazon.com/title/dp/B000TEST01?ref=search')
    item=result['groups'][0]['items'][0]
    item['source_url']=sources[0]['url']='https://www.amazon.com/dp/B000TEST01'
    item['rating']=None;item['review_count']=None
    assert agent.validate_result(result,sources,8000)['items'][0]['rating'] is None
    item['rating']=8
    assert not agent.validate_result(result,sources,8000)['items']
