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


def execute(job_id, scenario, integration):
    store = None
    try:
        fixture = json.loads((ROOT / 'fixtures/shopping.json').read_text())
        if integration:
            from .memory import recall
            memory = asyncio.run(recall())
            store = Store()
        else:
            memory, store = fixture['memory'], MemoryStore()
        report = run(FixtureTools(scenario, store), store, memory, fixture['profile'])
        report.update(memory_backend='cognee' if integration else 'fixture', storage_backend='singlestore' if integration else 'memory')
        try: report['telemetry'] = telemetry(report)
        except Exception as exc: report['telemetry'] = {'error':type(exc).__name__}
        (LOCAL / f"run-{report['run_id']}.json").write_text(json.dumps(report,indent=2))
        with LOCK: JOBS[job_id] = {'state':'complete','report':report}
    except Exception as exc:
        with LOCK: JOBS[job_id] = {'state':'failed','error':f'{type(exc).__name__}: check local service logs and docs/LOCAL_SETUP.md'}
    finally:
        if store: store.close()


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
        if self.path != '/api/runs': return self.send({'error':'not_found'},404)
        origin=self.headers.get('Origin')
        allowed={f'http://localhost:{self.server.server_port}',f'http://127.0.0.1:{self.server.server_port}'}
        if origin and origin not in allowed: return self.send({'error':'origin_rejected'},403)
        if self.headers.get_content_type() != 'application/json': return self.send({'error':'json_required'},415)
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0 < length < 10000: raise ValueError()
            body=json.loads(self.rfile.read(length))
            scenario=body.get('scenario','happy'); integration=body.get('mode')=='integration'
            if scenario not in SCENARIOS or body.get('mode') not in ('integration','isolated'): raise ValueError()
            # Never replay fault cases into a persistent task namespace.
            if integration and scenario!='happy': return self.send({'error':'Use isolated mode for fault scenarios.'},400)
        except (ValueError,TypeError): return self.send({'error':'invalid_input'},400)
        with LOCK:
            if any(j['state']=='running' for j in JOBS.values()): return self.send({'error':'A run is already in progress.'},409)
            job_id=str(uuid.uuid4()); JOBS[job_id]={'state':'running'}
        WORKER.submit(execute,job_id,scenario,integration)
        return self.send({'id':job_id},202)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8787); args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Tokensand app: http://localhost:{args.port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); WORKER.shutdown()
