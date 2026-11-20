import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs
import threading
from http.server import ThreadingHTTPServer
import pytest
from cryptography.fernet import Fernet
from tokensand import auth, tenancy, calendar, observability as ledger, agent_api
from tokensand.server import Handler
from test_agent_http import call

@pytest.fixture(autouse=True)
def private_state(tmp_path,monkeypatch):
    monkeypatch.setattr(auth,'DB',tmp_path/'accounts.db')
    monkeypatch.setattr(auth,'LOCAL',tmp_path)
    monkeypatch.setattr(tenancy,'LOCAL',tmp_path)
    monkeypatch.setattr(ledger,'DB',tmp_path/'legacy.db')
    monkeypatch.setenv('GOOGLE_CLIENT_ID','test-client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET','test-secret')
    monkeypatch.setenv('UPNEXT_TOKEN_ENCRYPTION_KEY',Fernet.generate_key().decode())


def account(subject):
    uid=auth.digest('google:'+subject)
    sid='session-'+subject
    with auth.db() as c:
        c.execute('INSERT OR IGNORE INTO users VALUES(?,?,?,?)',(uid,subject,subject+'@example.com',subject))
        c.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?)',(auth.digest(sid),uid,time.time()+3600))
    return uid,{'Cookie':'upnext_session='+sid}

@pytest.fixture
def shopper():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown();server.server_close();thread.join()


def test_http_requires_session_and_blocks_cross_account_access(shopper):
    alice,ah=account('alice');bob,bh=account('bob')
    with tenancy.scope(alice):
        run=ledger.create_run('Private birthday','demo')
        run['status']='completed';ledger.save(run)
    for path in ['/api/agent/conversations','/api/calendar','/api/agent/status']:
        assert call(shopper,path)[0]==401
    assert call(shopper,'/api/agent/runs/'+run['id'],headers=ah)[0]==200
    assert call(shopper,'/api/agent/runs/'+run['id'],headers={**bh,'X-UpNext-User':alice})[0]==404
    assert call(shopper,'/api/agent/conversations/'+run['conversation_id'],headers=bh)[1]['runs']==[]
    assert call(shopper,'/api/agent/runs',{'message':'steal','conversation_id':run['conversation_id']},bh)[0]==400
    assert call(shopper,'/api/agent/feedback',{'run_id':run['id'],'value':'helpful'},bh)[0]==400
    assert call(shopper,'/api/agent/preferences',{'preferences':'Only mine'},ah)[0]==200
    assert call(shopper,'/api/agent/status',headers=bh)[1]['settings']['preferences']==''
    assert call(shopper,'/api/agent/preferences',{'preferences':'CSRF'}, {**ah,'Origin':'https://evil.example'})[0]==403
    assert call(shopper,'/api/agent/preferences',{'preferences':'CSRF'}, {**ah,'Origin':''})[0]==403
    assert call(shopper,'/auth/logout',{},ah)[0]==200
    assert call(shopper,'/api/agent/status',headers=ah)[0]==401


def test_workers_and_telemetry_preserve_account_context():
    alice,_=account('alice');bob,_=account('bob')
    with ThreadPoolExecutor(max_workers=1) as pool:
        with tenancy.scope(alice):
            future=tenancy.enqueue(pool,ledger.create_run,'Alice birthday','demo')
        result=future.result()
        with tenancy.scope(bob):
            assert not ledger.get(result['id'])
            bid=ledger.analytics_id()
        with tenancy.scope(alice):
            assert ledger.get(result['id'])
            assert ledger.analytics_id()!=bid
            with pytest.raises(ValueError):ledger.set_settings({'memory_backend':'cognee'})
        assert pool.submit(tenancy.USER.get).result() is None


class BrowserHandler:
    def __init__(self,cookies='',path='/'):
        self.headers={'Cookie':cookies};self.path=path;self.response_headers={}
    def send_response(self,status):self.status=status
    def send_header(self,k,v):self.response_headers.setdefault(k,[]).append(v)
    def end_headers(self):pass
    def send(self,payload,status=200):self.status=status;self.payload=payload


def flow(purpose='login',cookies=''):
    h=BrowserHandler(cookies)
    auth.start(h,purpose)
    query=parse_qs(urlparse(h.response_headers['Location'][0]).query)
    browser=h.response_headers['Set-Cookie'][0].split(';')[0]
    return query, BrowserHandler(browser+('; '+cookies if cookies else ''),'/auth/google/callback?state='+query['state'][0]+'&code=fake-code')


def test_oauth_login_state_pkce_session_and_replay(monkeypatch):
    query,h=flow()
    assert query['scope']==['openid email profile'] and query['code_challenge_method']==['S256']
    monkeypatch.setattr(auth,'exchange',lambda code,verifier:{'id_token':'signed'})
    monkeypatch.setattr(auth,'verify',lambda token,nonce:{'sub':'alice','email':'alice@example.com','name':'Alice'})
    auth.callback(h)
    assert h.response_headers['Location']==['/']
    session=h.response_headers['Set-Cookie'][0]
    assert 'HttpOnly' in session and 'SameSite=Lax' in session
    assert auth.user(BrowserHandler(session.split(';')[0]))['email']=='alice@example.com'
    h.response_headers={};auth.callback(h)
    assert h.response_headers['Location']==['/?connection=failed']


@pytest.mark.parametrize('failure',['cookie','expired','nonce','denied'])
def test_oauth_rejects_invalid_flow(failure,monkeypatch):
    query,h=flow()
    if failure=='cookie':h.headers['Cookie']='upnext_oauth=wrong'
    if failure=='expired':
        with auth.db() as c:c.execute('UPDATE oauth SET expires=0')
    if failure=='denied':h.path+='&error=access_denied'
    monkeypatch.setattr(auth,'exchange',lambda *args:{'id_token':'token'})
    monkeypatch.setattr(auth.id_token,'verify_oauth2_token',lambda *args:{'sub':'alice','email_verified':True,'nonce':'wrong'})
    auth.callback(h)
    assert h.response_headers['Location']==['/?connection=failed']
    assert not auth.users()


@pytest.mark.parametrize('wrong_account,missing_scope',[(True,False),(False,True),(False,False)])
def test_calendar_grant_is_bound_to_signed_in_user(wrong_account,missing_scope,monkeypatch):
    alice,headers=account('alice')
    q,h=flow('calendar',headers['Cookie'])
    assert q['access_type']==['offline'] and auth.CALENDAR_SCOPE in q['scope'][0]
    monkeypatch.setattr(auth,'exchange',lambda *args:{'id_token':'token','refresh_token':'private-refresh','scope':'' if missing_scope else auth.CALENDAR_SCOPE})
    monkeypatch.setattr(auth,'verify',lambda *args:{'sub':'bob' if wrong_account else 'alice'})
    auth.callback(h)
    assert auth.connected(alice)==(not wrong_account and not missing_scope)
    assert b'private-refresh' not in auth.DB.read_bytes()


def test_airbyte_reads_only_account_credentials_and_snapshots(monkeypatch):
    alice,_=account('alice');bob,_=account('bob')
    auth.save_grant(alice,'alice-token');auth.save_grant(bob,'bob-token')
    def connector(command,files):
        assert files['config']['credentials']['refresh_token']=='alice-token'
        assert files['config']['credentials']['auth_type']=='manual'
        if command=='discover':return [{'catalog':{'streams':[{'name':'events','json_schema':{'type':'object'}}]}}]
        assert len(files['catalog']['streams'])==1
        return [{'trace':{'stream_status':{'status':'COMPLETE'}}}]
    monkeypatch.setattr(calendar,'connector',connector)
    with tenancy.scope(alice):
        calendar.sync();assert calendar.view()['synced_at']
        auth.disconnect(alice);assert not calendar.view()['connected'] and calendar.view()['synced_at'] is None
    with tenancy.scope(bob):
        assert calendar.view()['connected'] and calendar.view()['synced_at'] is None
        assert auth.grant(bob)['refresh_token']=='bob-token'


def test_agent_job_runs_in_account_and_keeps_history_private(monkeypatch):
    alice,_=account('alice');bob,_=account('bob')
    executed=[]
    def execute(run_id):
        run=ledger.get(run_id)
        executed.append((tenancy.USER.get(),run['messages'][0]['content']))
        run['status']='completed';ledger.save(run)
    monkeypatch.setattr(agent_api.agent,'execute',execute)
    with tenancy.scope(alice):
        run=agent_api.submit('My private event','demo')
    # One-worker executor: sentinel waits for the queued run to finish.
    agent_api.POOL.submit(lambda:None).result(timeout=5)
    assert executed==[(alice,'My private event')]
    with tenancy.scope(bob):assert ledger.conversations()==[]
    with tenancy.scope(alice):assert ledger.get(run['id'])['status']=='completed'


def test_expired_session_and_secure_cookie(shopper,monkeypatch):
    uid,headers=account('expired')
    with auth.db() as c:c.execute('UPDATE sessions SET expires=0')
    assert call(shopper,'/api/calendar',headers=headers)[0]==401
    monkeypatch.setenv('UPNEXT_APP_URL','https://upnext.example')
    assert '; Secure' in auth.cookie_header('upnext_session','opaque',60)


def test_verified_identity_requires_nonce_and_verified_email(monkeypatch):
    claims={'sub':'alice','email_verified':False,'nonce':'expected'}
    monkeypatch.setattr(auth.id_token,'verify_oauth2_token',lambda *args:claims)
    with pytest.raises(ValueError):auth.verify('token','expected')
    claims['email_verified']=True
    with pytest.raises(ValueError):auth.verify('token','wrong')
    assert auth.verify('token','expected')['sub']=='alice'
