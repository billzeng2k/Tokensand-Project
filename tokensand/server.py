"""Standalone local web app. Serves only explicit web assets, never repo secrets."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import uuid
from urllib.parse import urlparse
from .config import ROOT, LOCAL
from .storage import Store, MemoryStore
from .tools import FixtureTools, SCENARIOS
from .workflow import run, telemetry
from . import agent_api, auth, tenancy

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
    admin_surface = False
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        super().end_headers()
    def send(self, value, status=200):
        data=json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers(); self.wfile.write(data)
    def valid_host(self):
        return self.headers.get('Host') in {f'localhost:{self.server.server_port}', f'127.0.0.1:{self.server.server_port}'}
    def log_message(self, format, *args):
        # BaseHTTPRequestHandler otherwise logs OAuth callback codes in request URLs.
        pass
    def do_GET(self):
        path=urlparse(self.path).path
        if not self.valid_host():return self.send({'error':'host_rejected'},403)
        if not self.admin_surface:
            if path=='/auth/me':
                account=auth.user(self)
                return self.send({'user':{k:account[k] for k in ('name','email')} if account else None,'configured':auth.configured()})
            if path=='/auth/google/start':return auth.start(self,'login')
            if path=='/auth/google/calendar':return auth.start(self,'calendar')
            if path=='/auth/google/callback':return auth.callback(self)
        self.scoped_request(self.get_scoped, path)
    def scoped_request(self, fn, path):
        uid=None
        if not self.admin_surface and path.startswith('/api/'):
            account=auth.user(self)
            if not account:return self.send({'error':'Sign in with Google to continue.'},401)
            uid=account['id']
        if self.admin_surface and path.startswith('/api/'):
            uid=self.headers.get('X-UpNext-User') or None
            if uid and (not agent_api.admin_allowed(self) or uid not in {u['id'] for u in auth.users()}):
                return self.send({'error':'Account not found'},404)
        with tenancy.scope(uid):
            return fn()
    def get_scoped(self):
        if not self.valid_host(): return self.send({'error':'host_rejected'},403)
        path=urlparse(self.path).path
        if self.admin_surface:
            if path.startswith('/api/') and not path.startswith(('/api/admin/','/api/runs/')) and path not in ('/api/config','/api/calendar'):return self.send({'error':'not_found'},404)
        elif path.startswith(('/api/admin/','/api/runs/')) or path=='/api/config':return self.send({'error':'not_found'},404)
        if self.admin_surface and path.startswith('/api/') and not path.startswith('/api/admin/') and not agent_api.admin_allowed(self):return self.send({'error':'Admin sign-in required'},401)
        if agent_api.get(self,path): return
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
        files=({'/':('admin.html','text/html'),'/admin':('admin.html','text/html'),'/lab':('index.html','text/html'),'/admin.js':('admin.js','text/javascript'),'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css'),'/console.css':('console.css','text/css')} if self.admin_surface else {'/':('agent.html','text/html'),'/agent.js':('agent.js','text/javascript'),'/calendar-view.js':('calendar-view.js','text/javascript'),'/console.css':('console.css','text/css')})
        if path not in files: return self.send({'error':'not_found'},404)
        filename, content_type=files[path]
        data=(ROOT / 'web' / filename).read_bytes()
        self.send_response(200); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        if not self.valid_host():return self.send({'error':'host_rejected'},403)
        allowed={f'http://localhost:{self.server.server_port}',f'http://127.0.0.1:{self.server.server_port}'}
        if self.headers.get('Origin') not in allowed:return self.send({'error':'origin_rejected'},403)
        self.scoped_request(self.post_scoped,self.path)
    def post_scoped(self):
        if not self.valid_host(): return self.send({'error':'host_rejected'},403)
        origin=self.headers.get('Origin')
        allowed={f'http://localhost:{self.server.server_port}',f'http://127.0.0.1:{self.server.server_port}'}
        if origin and origin not in allowed: return self.send({'error':'origin_rejected'},403)
        if self.headers.get_content_type() != 'application/json': return self.send({'error':'json_required'},415)
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0 < length < 10000: raise ValueError()
            body=json.loads(self.rfile.read(length))
            if not isinstance(body, dict): raise ValueError()
            if not self.admin_surface and self.path=='/auth/logout':return auth.logout(self)
            if self.admin_surface:
                if not self.path.startswith('/api/admin/') and self.path not in ('/api/runs','/api/calendar/sync'):return self.send({'error':'not_found'},404)
                if not self.path.startswith('/api/admin/') and not agent_api.admin_allowed(self):return self.send({'error':'Admin sign-in required'},401)
            elif self.path in ('/api/calendar/sync','/api/calendar/disconnect'):
                if self.path.endswith('/disconnect'):
                    auth.disconnect(tenancy.USER.get());return self.send({'ok':True})
                try:
                    from .calendar import sync
                    return self.send(sync())
                except Exception:
                    return self.send({'error':'Calendar sync failed. Retry or reconnect Google Calendar. Your previous snapshot was preserved.'},502)
            elif not self.path.startswith('/api/agent/'):return self.send({'error':'not_found'},404)
            if agent_api.post(self,self.path,body): return
            if self.path not in ('/api/runs','/api/calendar/sync'): return self.send({'error':'not_found'},404)
            if self.path == '/api/calendar/sync':
                with LOCK:
                    if any(j['state']=='running' for j in JOBS.values()): return self.send({'error':'A run is already in progress.'},409)
                    job_id=str(uuid.uuid4()); JOBS[job_id]={'state':'running'}
                tenancy.enqueue(WORKER,sync_calendar, job_id)
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
        tenancy.enqueue(WORKER,execute,job_id,scenario,integration,event_id)
        return self.send({'id':job_id},202)

class AdminHandler(Handler):
    admin_surface = True


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8787);parser.add_argument('--admin-port',type=int,default=8788);args=parser.parse_args()
    agent_api.ensure_admin_token()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    admin=ThreadingHTTPServer(('127.0.0.1',args.admin_port),AdminHandler)
    threading.Thread(target=admin.serve_forever,daemon=True).start()
    if os.getenv('AMAZON_RETRIEVAL')=='browser':
        from .amazon_bridge import start
        start()
    agent_api.startup()
    print(f'UpNext app: http://localhost:{args.port}',flush=True)
    print(f'Private admin: http://localhost:{args.admin_port} (run npm run admin:token for your local sign-in token)',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();admin.shutdown();admin.server_close();agent_api.STOP.set();WORKER.shutdown();agent_api.POOL.shutdown()
