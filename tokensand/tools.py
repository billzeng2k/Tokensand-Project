import copy
import json
import os
import urllib.request
from .config import ROOT

SCENARIOS = ['happy', 'sold-out', 'price-increase', 'unknown-delivery', 'cancelled', 'timeout-after-save']

class FixtureTools:
    """Local synthetic services. These are not Firedrill-hosted tools."""
    mode = 'local-fixture'
    def __init__(self, scenario='happy', store=None):
        if scenario not in SCENARIOS:
            raise ValueError('Unknown scenario')
        self.data = json.loads((ROOT / 'fixtures/shopping.json').read_text())
        self.scenario = scenario
        self.store = store
        self.timed_out = False
    def invoke(self, service, operation, arguments, key=None):
        if operation == 'events.get':
            event = copy.deepcopy(self.data['event'])
            if arguments['event_id'] != event['id']:
                raise ValueError('Unknown event_id')
            if self.scenario == 'cancelled':
                event['status'] = 'cancelled'
            return event
        if operation == 'products.search':
            return copy.deepcopy(self.data['products'])
        if operation == 'products.get':
            p = copy.deepcopy(next(p for p in self.data['products'] if p['id'] == arguments['product_id']))
            if p['id'] == 'cotton-jacket':
                if self.scenario == 'sold-out': p['in_stock'] = False
                if self.scenario == 'price-increase': p['price_cents'] = 9900
                if self.scenario == 'unknown-delivery': p['delivery_date'] = None
            return p
        if operation == 'tasks.create':
            result = self.store.save_task(key, arguments)
            if self.scenario == 'timeout-after-save' and not self.timed_out:
                self.timed_out = True
                raise TimeoutError('Synthetic timeout after task was saved')
            return result
        if operation == 'tasks.get':
            return self.store.get_task(arguments['task_key'])
        raise ValueError('Unsupported operation')

class FiredrillTools:
    mode = 'firedrill-synthetic'
    def __init__(self):
        self.urls = {s: os.environ[f'{s.upper()}_INVOKE_URL'] for s in ('calendar', 'shopping')}
        if not all(self.urls.values()):
            raise RuntimeError('Both Firedrill dependency routes are required. No fallback to fixtures.')
    def invoke(self, service, operation, arguments, key=None):
        body = {'operation': operation, 'arguments': arguments}
        if key: body['idempotency_key'] = key
        request = urllib.request.Request(self.urls[service], json.dumps(body).encode(), {'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
