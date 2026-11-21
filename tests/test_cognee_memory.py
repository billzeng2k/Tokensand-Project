import json
from types import SimpleNamespace
from tokensand import cognee_memory as m,tenancy

def test_worker_isolation_and_exact_snapshot(tmp_path,monkeypatch):
    monkeypatch.setattr(tenancy,'LOCAL',tmp_path)
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        return SimpleNamespace(returncode=0,stdout='UPNEXT_MEMORY='+kwargs['input'])
    monkeypatch.setattr(m.subprocess,'run',run)
    snapshot={'explicit_preferences':['blue'],'purchased_items':[]}
    with tenancy.scope('a'*64):assert m.recall(snapshot,'event')==snapshot
    with tenancy.scope('b'*64):assert m.recall(snapshot,'event')==snapshot
    assert calls[0][1]['env']['SYSTEM_ROOT_DIRECTORY']!=calls[1][1]['env']['SYSTEM_ROOT_DIRECTORY']
    assert calls[0][1]['env']['IMPROVE_AUTO_ENABLED']=='false'

def test_mismatch_rejected(tmp_path,monkeypatch):
    import pytest
    monkeypatch.setattr(tenancy,'LOCAL',tmp_path)
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout='UPNEXT_MEMORY={}'))
    with tenancy.scope('a'*64),pytest.raises(RuntimeError,match='snapshot_mismatch'):m.recall({'purchased_items':['x']})
