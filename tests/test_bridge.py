import json
import os
import subprocess
import sys
import threading
from tokensand.config import ROOT
from tokensand.mock_server import make_server


def test_firedrill_protocol_and_stateful_http_recovery():
    server = make_server('timeout-after-save')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = {**os.environ, 'TOKENSAND_NO_DOTENV':'1', 'CALENDAR_INVOKE_URL':f'http://127.0.0.1:{server.server_port}/calendar', 'SHOPPING_INVOKE_URL':f'http://127.0.0.1:{server.server_port}/shopping'}
        requests = [{'id':f'step-{i}','session':'test','kind':'message','input':{'event_id':'holiday-dinner-demo'}} for i in (1,2)]
        proc = subprocess.run([sys.executable,'-m','tokensand.bridge'],cwd=ROOT,env=env,input=''.join(json.dumps(r)+'\n' for r in requests),text=True,capture_output=True,timeout=20,check=True)
        lines = proc.stdout.splitlines()
        assert lines[0] == 'READY'
        results = [json.loads(l) for l in lines[1:]]
        assert [r['id'] for r in results] == ['step-1','step-2']
        assert results[0]['output']['status'] == 'task_saved'
        assert results[1]['output']['status'] == 'already_saved'
        assert results[0]['output']['task']['task_key'] == results[1]['output']['task']['task_key']
    finally:
        server.shutdown(); server.server_close(); thread.join()
