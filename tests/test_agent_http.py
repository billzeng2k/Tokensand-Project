import json
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
import pytest
from tokensand import observability as ledger,agent_api
from tokensand.server import Handler

@pytest.fixture
def http(tmp_path,monkeypatch):
    monkeypatch.setattr(ledger,'DB',tmp_path/'http.db')
    monkeypatch.setenv('UPNEXT_ADMIN_TOKEN','test-admin-token')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown();server.server_close();thread.join()


def call(base,path,body=None,headers=None):
    request=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
    try:
        with urllib.request.urlopen(request) as r:return r.status,json.load(r),r.headers
    except urllib.error.HTTPError as r:return r.code,json.load(r),r.headers


def test_admin_auth_and_same_origin(http):
    assert call(http,'/api/admin/settings')[0]==401
    assert call(http,'/api/admin/login',{'token':'wrong'})[0]==401
    code,_,headers=call(http,'/api/admin/login',{'token':'test-admin-token'})
    assert code==200 and 'HttpOnly' in headers['Set-Cookie']
    cookie=headers['Set-Cookie'].split(';')[0]
    assert call(http,'/api/admin/settings',headers={'Cookie':cookie})[0]==200
    assert call(http,'/api/admin/settings',{'agent_enabled':False},headers={'Cookie':cookie,'Origin':'https://attacker.example'})[0]==403
    assert call(http,'/api/agent/status',headers={'Host':'attacker.example'})[0]==403
    assert call(http,'/.env')[0]==404


def test_invalid_message_has_no_run(http):
    assert call(http,'/api/agent/runs',{'message':'','mode':'demo'})[0]==400
    assert not ledger.query()
