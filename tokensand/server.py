"""Standalone local web app. Serves only explicit web assets, never repo secrets."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import uuid
from urllib.parse import urlparse
from .config import ROOT, LOCAL
from .storage import Store, MemoryStore
from .tools import FixtureTools, SCENARIOS
from .workflow import run, telemetry

JOBS = {}
LOCK = threading.Lock()
WORKER = ThreadPoolExecutor(max_workers=1)


def execute(job_id, scenario, integration, event_id=None):
    store = None
    try:
        fixture = json.loads((ROOT / 'fixtures/shopping.json').read_text())
        if integration:
            from .memory import recall
            memory = asyncio.run(recall())
            store = Store()
        else:
            memory, store = fixture['memory'], MemoryStore()
        tools = FixtureTools(scenario, store)
        if event_id:
            from .calendar import selected_event
            tools.data['event'] = selected_event(event_id)
            tools.mode = 'airbyte-calendar-synthetic-shopping'
        report = run(tools, store, memory, fixture['profile'], event_id or 'holiday-dinner-demo')
        report.update(memory_backend='cognee' if integration else 'fixture', storage_backend='singlestore' if integration else 'memory')
        try: report['telemetry'] = telemetry(report)
        except Exception as exc: report['telemetry'] = {'error':type(exc).__name__}
        (LOCAL / f"run-{report['run_id']}.json").write_text(json.dumps(report,indent=2))
        with LOCK: JOBS[job_id] = {'state':'complete','report':report}
    except Exception as exc:
        with LOCK: JOBS[job_id] = {'state':'failed','error':f'{type(exc).__name__}: check local service logs and docs/LOCAL_SETUP.md'}
    finally:
        if store: store.close()


def sync_calendar(job_id):
    try:
        from .calendar import sync
        result = sync()
        with LOCK: JOBS[job_id] = {'state':'complete', 'calendar':result}
    except Exception:
        with LOCK: JOBS[job_id] = {'state':'failed', 'error':'Calendar sync failed. Connect Google with npm run calendar:connect and check docs/AIRBYTE.md. Previous snapshot preserved.'}


class Handler(BaseHTTPRequestHandler):
    def send(self, value, status=200):
        data=json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        path=urlparse(self.path).path
        if path == '/api/calendar':
            from .calendar import view
            return self.send(view())
        if path == '/api/config':
            fixture=json.loads((ROOT / 'fixtures/shopping.json').read_text())
            return self.send({'scenarios':SCENARIOS,'fixture':fixture})
        if path.startswith('/api/runs/'):
            job_id=path.rsplit('/',1)[-1]
            with LOCK: job=JOBS.get(job_id)
            return self.send(job or {'error':'not_found'},200 if job else 404)
        files={'/':('index.html','text/html'),'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css')}
        if path not in files: return self.send({'error':'not_found'},404)
        filename, content_type=files[path]
        data=(ROOT / 'web' / filename).read_bytes()
        self.send_response(200); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        if self.path not in ('/api/runs', '/api/calendar/sync'): return self.send({'error':'not_found'},404)
        origin=self.headers.get('Origin')
        allowed={f'http://localhost:{self.server.server_port}',f'http://127.0.0.1:{self.server.server_port}'}
        if origin and origin not in allowed: return self.send({'error':'origin_rejected'},403)
        if self.headers.get_content_type() != 'application/json': return self.send({'error':'json_required'},415)
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0 < length < 10000: raise ValueError()
            body=json.loads(self.rfile.read(length))
            if not isinstance(body, dict): raise ValueError()
            if self.path == '/api/calendar/sync':
                with LOCK:
                    if any(j['state']=='running' for j in JOBS.values()): return self.send({'error':'A run is already in progress.'},409)
                    job_id=str(uuid.uuid4()); JOBS[job_id]={'state':'running'}
                WORKER.submit(sync_calendar, job_id)
                return self.send({'id':job_id},202)
            event_id=body.get('event_id')
            if event_id is not None and (not isinstance(event_id, str) or len(event_id)!=64): raise ValueError()
            if event_id and body.get('scenario','happy')!='happy': raise ValueError()
            scenario=body.get('scenario','happy'); integration=body.get('mode')=='integration'
            if scenario not in SCENARIOS or body.get('mode') not in ('integration','isolated'): raise ValueError()
            # Never replay fault cases into a persistent task namespace.
            if integration and scenario!='happy': return self.send({'error':'Use isolated mode for fault scenarios.'},400)
        except (ValueError,TypeError): return self.send({'error':'invalid_input'},400)
        with LOCK:
            if any(j['state']=='running' for j in JOBS.values()): return self.send({'error':'A run is already in progress.'},409)
            job_id=str(uuid.uuid4()); JOBS[job_id]={'state':'running'}
        WORKER.submit(execute,job_id,scenario,integration,event_id)
        return self.send({'id':job_id},202)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8787); args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'UpNext app: http://localhost:{args.port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); WORKER.shutdown()
