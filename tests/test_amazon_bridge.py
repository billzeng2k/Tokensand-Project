import threading
import time
import pytest
from tokensand import amazon_bridge as bridge

@pytest.mark.parametrize('url',['http://www.amazon.com/s?k=a','https://evil.test/s','https://www.amazon.com@evil.test/s','https://www.amazon.com/gp/cart/view.html'])
def test_destination_allowlist(url):
    assert not bridge.valid_url(url)

def test_disconnected_companion_fails_immediately(monkeypatch):
    monkeypatch.setattr(bridge,'LAST_SEEN',0)
    with pytest.raises(RuntimeError,match='amazon_companion_unavailable'):bridge.read('https://www.amazon.com/s?k=carrier')

def test_queue_returns_only_its_result_and_cleans_up(monkeypatch):
    monkeypatch.setattr(bridge,'LAST_SEEN',time.monotonic())
    result=[]
    worker=threading.Thread(target=lambda:result.append(bridge.read('https://www.amazon.com/s?k=carrier',2)))
    worker.start()
    for _ in range(100):
        with bridge.LOCK:
            if bridge.JOBS:
                job=next(iter(bridge.JOBS.values()));job['result']={'text':'actual page'};job['event'].set();break
        time.sleep(.01)
    worker.join(3)
    assert result==[{'text':'actual page'}] and not bridge.JOBS

def test_timeout_removes_pending_job(monkeypatch):
    monkeypatch.setattr(bridge,'LAST_SEEN',time.monotonic())
    with pytest.raises(RuntimeError,match='amazon_companion_timeout'):bridge.read('https://www.amazon.com/s?k=carrier',.01)
    assert not bridge.JOBS


def test_http_bridge_requires_capability_and_matching_pending_job(monkeypatch):
    import http.client
    import json
    from http.server import ThreadingHTTPServer
    monkeypatch.setattr(bridge,'token',lambda:'test-capability')
    server=ThreadingHTTPServer(('127.0.0.1',0),bridge.Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def request(method,path,data=None,auth='Bearer test-capability',host='127.0.0.1:8789'):
        client=http.client.HTTPConnection('127.0.0.1',server.server_port)
        client.request(method,path,body=json.dumps(data) if data else None,headers={'Host':host,'Authorization':auth})
        response=client.getresponse();status=response.status;body=json.loads(response.read());client.close();return status,body
    try:
        assert request('GET','/next',auth='Bearer wrong')[0]==401
        assert request('GET','/next',host='evil.example')[0]==401
        assert request('POST','/result',{'id':'not-a-job','result':None})[0]==409
        with bridge.LOCK:bridge.JOBS['test-job']={'id':'test-job','url':'https://www.amazon.com/dp/B000000001','event':threading.Event(),'claimed':False,'result':None}
        assert request('GET','/next')[1]['id']=='test-job'
        assert request('GET','/next')[1] is None
        assert request('POST','/result',{'id':'test-job','result':{'url':'https://evil.example','text':'fake','links':[]}})[0]==400
        assert not bridge.JOBS['test-job']['event'].is_set()
        assert request('POST','/result',{'id':'test-job','result':None})[0]==200
        assert request('POST','/result',{'id':'test-job','result':None})[0]==409
    finally:
        with bridge.LOCK:bridge.JOBS.pop('test-job',None)
        server.shutdown();server.server_close();thread.join()
