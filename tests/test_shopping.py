import json
import pytest
from tokensand import observability as ledger,shopping,tenancy

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(ledger,'DB',tmp_path/'traces.db')
    monkeypatch.setattr(tenancy,'LOCAL',tmp_path)

def recommendation(event='a'*64):
    run=ledger.create_run('Help with dinner','live',event_id=event)
    item={'name':'Carrier','source_url':'https://www.amazon.com/dp/B000000001','price_cents':1999,'currency':'USD','rating':4.5,'review_count':100,'reason':'Carry dinner','uncertainties':[]}
    run.update(status='completed',result={'items':[item]},context={'event':{'title':'Dinner'}});ledger.save(run)
    return run,item

def test_purchase_is_durable_idempotent_and_can_be_undone():
    run,item=recommendation()
    a=shopping.decide(run['id'],item['source_url'],'purchased')['decisions'][0]
    b=shopping.decide(run['id'],item['source_url'],'purchased')['decisions'][0]
    assert a==b and a['purchase_source']=='user_reported'
    assert shopping.context('other')['purchased_items'][0]['name']=='Carrier'
    assert shopping.decide(run['id'],item['source_url'],'undo')['decisions']==[]
    assert not shopping.context('other')['purchased_items']

def test_dismissal_is_event_scoped_not_inferred_brand_dislike():
    run,item=recommendation()
    shopping.decide(run['id'],item['source_url'],'dismissed')
    assert shopping.context('a'*64)['dismissed_for_this_event']
    assert not shopping.context('b'*64)['dismissed_for_this_event']
    assert not shopping.context('a'*64)['explicit_preferences']

def test_cannot_forge_product_or_write_other_users_purchase():
    with tenancy.scope('a'*64):run,item=recommendation()
    with tenancy.scope('b'*64):
        with pytest.raises(ValueError):shopping.decide(run['id'],item['source_url'],'purchased')
        assert shopping.state()['decisions']==[]
    with tenancy.scope('a'*64):
        with pytest.raises(ValueError):shopping.decide(run['id'],'https://www.amazon.com/dp/B000000002','purchased')

def test_preference_memory_persists_isolates_and_forgets():
    with tenancy.scope('a'*64):
        shopping.remember('I prefer blue');shopping.remember('I prefer blue')
        assert len(shopping.state()['notes'])==1
        note=shopping.state()['notes'][0]
    with tenancy.scope('b'*64):
        assert shopping.context(None)['explicit_preferences']==[]
        shopping.forget(note['id'])
    with tenancy.scope('a'*64):
        assert shopping.context(None)['explicit_preferences']==['I prefer blue']
        shopping.forget(note['id']);assert not shopping.state()['notes']

def test_conversation_cannot_be_reused_for_another_event():
    run,_=recommendation()
    with pytest.raises(ValueError,match='different event'):ledger.create_run('More','live',run['conversation_id'],event_id='b'*64)
