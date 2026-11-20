"""Firedrill jsonl-process.v1 adapter. Process-isolated policy testing only."""
import json
import sys
from .config import ROOT
from .storage import MemoryStore
from .tools import FiredrillTools
from .workflow import run


def main():
    # No Cognee/DB/analytics in this profile: all mutable target state is process-only.
    # Tests the same decision and reconciliation code as the local integration run.
    store = MemoryStore()
    tools = FiredrillTools()
    fixture = json.loads((ROOT / 'fixtures/shopping.json').read_text())
    print('READY', flush=True)
    for line in sys.stdin:
        request = {}
        try:
            request = json.loads(line)
            payload = request['input']
            if isinstance(payload, str): payload = json.loads(payload)
            if not isinstance(payload, dict): raise ValueError('input must be a JSON object')
            report = run(tools, store, payload.get('memory', fixture['memory']), payload.get('profile', fixture['profile']), payload.get('event_id','holiday-dinner-demo'))
            print(json.dumps({'id':request['id'],'output':report}), flush=True)
        except Exception as exc:
            print(json.dumps({'id':request.get('id'),'error':f'{type(exc).__name__}: {exc}'}), flush=True)

if __name__ == '__main__': main()
