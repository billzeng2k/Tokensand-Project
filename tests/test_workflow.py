import json
import pytest
from tokensand.config import ROOT
from tokensand.storage import MemoryStore
from tokensand.tools import FixtureTools
from tokensand.workflow import run

@pytest.fixture
def fixture(): return json.loads((ROOT / 'fixtures/shopping.json').read_text())

def execute(fixture, scenario='happy', store=None):
    store = store or MemoryStore()
    return run(FixtureTools(scenario, store), store, fixture['memory'], fixture['profile']), store

def test_happy_and_memory_exclusion(fixture):
    report, store = execute(fixture)
    assert report['status'] == 'task_saved'
    assert report['task']['product']['id'] == 'cotton-jacket'
    assert report['task']['order_placed'] is False
    assert any('remembered_wool_rejection' in d['reasons'] for d in report['decisions'])
    assert len(store.tasks) == 1

@pytest.mark.parametrize('scenario', ['sold-out','price-increase','unknown-delivery'])
def test_revalidate_before_action(fixture, scenario):
    report, store = execute(fixture, scenario)
    assert report['status'] == 'no_eligible_product'
    assert not store.tasks

def test_cancelled_event_creates_nothing(fixture):
    report, store = execute(fixture, 'cancelled')
    assert report['status'] == 'event_cancelled'
    assert not store.tasks

def test_timeout_after_save_is_reconciled(fixture):
    report, store = execute(fixture, 'timeout-after-save')
    assert report['status'] == 'task_saved'
    assert len(store.tasks) == 1
    assert sum(s['operation']=='tasks.create' for s in report['steps']) == 1

def test_repeat_does_not_duplicate(fixture):
    _, store = execute(fixture)
    report, store = execute(fixture, store=store)
    assert report['status'] == 'already_saved'
    assert len(store.tasks) == 1

def test_unconfirmed_write_does_not_claim_success(fixture):
    class MissingSave(FixtureTools):
        def invoke(self, service, operation, arguments, key=None):
            if operation == 'tasks.create': raise TimeoutError()
            return super().invoke(service, operation, arguments, key)
    store = MemoryStore()
    report = run(MissingSave(store=store), store, fixture['memory'], fixture['profile'])
    assert report['status'] == 'action_unconfirmed'
    assert not store.tasks
