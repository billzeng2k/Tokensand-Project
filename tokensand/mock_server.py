"""Loopback-only synthetic tool service for transport tests, not Firedrill cloud."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .storage import MemoryStore
from .tools import FixtureTools, SCENARIOS


def make_server(scenario='happy', port=0):
    tools = FixtureTools(scenario, MemoryStore())
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args): pass
        def do_POST(self):
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 100_000: raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(length))
                service = self.path.strip('/').split('/')[0]
                if service not in ('calendar','shopping'): raise ValueError('Unknown route')
                result = tools.invoke(service, body['operation'], body['arguments'], body.get('idempotency_key'))
                status = 200
            except TimeoutError:
                result, status = {'error':'synthetic_timeout_after_save'}, 504
            except Exception as exc:
                result, status = {'error':type(exc).__name__}, 400
            payload = json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    return ThreadingHTTPServer(('127.0.0.1',port), Handler)

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--scenario', choices=SCENARIOS, default='happy')
    parser.add_argument('--port',type=int,default=8091)
    args=parser.parse_args()
    server=make_server(args.scenario,args.port)
    print(f'Local fixture HTTP server: http://127.0.0.1:{server.server_port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
