"""Loopback-only, capability-authenticated Amazon browser companion queue.

Only public Amazon URLs cross this boundary, never calendar/user context.
"""
import hmac
import json
import secrets
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from .config import LOCAL

LOCK=threading.Lock()
JOBS={}
LAST_SEEN=0.0

def valid_url(url):
    p=urlsplit(url)
    return p.scheme=='https' and p.netloc=='www.amazon.com' and (p.path=='/s' or bool(re.fullmatch(r'/dp/[A-Z0-9]{10}',p.path)))

def token():
    path=LOCAL/'amazon-bridge-token'
    if not path.exists():
        LOCAL.mkdir(parents=True,exist_ok=True)
        try:
            with open(path,'x') as f:
                path.chmod(0o600);f.write(secrets.token_urlsafe(32))
        except FileExistsError:pass
    return path.read_text().strip()

def read(url,timeout=60):
    if not valid_url(url):raise ValueError('invalid_amazon_url')
    if time.monotonic()-LAST_SEEN>10:raise RuntimeError('amazon_companion_unavailable')
    jid=secrets.token_urlsafe(24);event=threading.Event()
    with LOCK:JOBS[jid]={'id':jid,'url':url,'event':event,'claimed':False,'result':None}
    try:
        if not event.wait(timeout):raise RuntimeError('amazon_companion_timeout')
        with LOCK:return JOBS[jid]['result']
    finally:
        with LOCK:JOBS.pop(jid,None)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,data,status=200):
        body=json.dumps(data).encode();self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def authorized(self):
        return self.headers.get('Host') in ('127.0.0.1:8789','localhost:8789') and hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token())
    def do_GET(self):
        global LAST_SEEN
        if not self.authorized():return self.send({'error':'unauthorized'},401)
        if self.path!='/next':return self.send({},404)
        with LOCK:
            LAST_SEEN=time.monotonic()
            for job in JOBS.values():
                if not job['claimed']:
                    job['claimed']=True
                    return self.send({'id':job['id'],'url':job['url']})
        self.send(None)
    def do_POST(self):
        global LAST_SEEN
        if not self.authorized():return self.send({'error':'unauthorized'},401)
        if self.path!='/result':return self.send({},404)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<200_000:raise ValueError()
            data=json.loads(self.rfile.read(size));jid=data['id']
            with LOCK:
                job=JOBS.get(jid)
                if not job or not job['claimed'] or job['event'].is_set():return self.send({},409)
                result=data.get('result')
                if result is not None:
                    if not isinstance(result,dict) or result.get('url')!=job['url']:raise ValueError()
                    if not isinstance(result.get('text'),str) or len(result['text'])>50000:raise ValueError()
                    links=result.get('links',[])
                    if not isinstance(links,list) or len(links)>100 or not all(isinstance(x,str) and valid_url(x) for x in links):raise ValueError()
                LAST_SEEN=time.monotonic()
                job['result']=result;job['event'].set()
            self.send({'ok':True})
        except (ValueError,KeyError,TypeError):self.send({'error':'invalid_result'},400)

def start():
    token()
    server=ThreadingHTTPServer(('127.0.0.1',8789),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server
