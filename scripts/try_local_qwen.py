"""Bounded local Qwen/Amazon experiment; no API keys, purchases, or cloud inference."""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tokensand.agent import SCHEMA, SYSTEM, validate_result

ROOT = Path(__file__).resolve().parents[1]

class PageText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'): self.skip+=1
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
    def handle_data(self, text):
        if not self.skip and text.strip(): self.parts.append(text.strip())

MODEL = 'qwen3:4b'

def model_call(messages, schema, audit):
    started=time.monotonic()
    body={'model':MODEL,'messages':messages,'format':schema,'stream':False,'think':False,
          'options':{'temperature':0,'num_ctx':8192,'num_predict':2200},'keep_alive':'5m'}
    req=urllib.request.Request('http://127.0.0.1:11434/api/chat',json.dumps(body).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=300) as response: result=json.load(response)
    if not result.get('done') or result.get('done_reason')=='length': raise RuntimeError('Incomplete local model response')
    parsed=json.loads(result['message']['content'])
    audit.append({'type':'local_model','model':result['model'],'duration_seconds':round(time.monotonic()-started,2),
                  'input_tokens':result.get('prompt_eval_count'), 'output_tokens':result.get('eval_count'),
                  'api_cost_usd':0,'output':parsed})
    return parsed

def read_amazon(url, audit):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname!='www.amazon.com' or parsed.username or parsed.port:
        raise ValueError('Only public www.amazon.com HTTPS URLs are allowed')
    # Redirects are rejected rather than following an untrusted destination.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args): return None
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'UpNext research prototype (read-only)'})
        with urllib.request.build_opener(NoRedirect).open(req,timeout=25) as response:
            raw=response.read(2_000_000).decode('utf-8',errors='replace')
        parser=PageText();parser.feed(raw);text=' '.join(parser.parts)
        blocked=any(x in text.lower() for x in ('enter the characters you see','sorry! something went wrong','robot check','verify that you are not a robot'))
        audit.append({'type':'amazon_read','url':url,'status':'blocked' if blocked else 'retrieved','observed_at':datetime.now(timezone.utc).isoformat()})
        return None if blocked else (raw,text)
    except (urllib.error.URLError,TimeoutError) as exc:
        audit.append({'type':'amazon_read','url':url,'status':'unavailable','http_status':getattr(exc,'code',None)})
        return None

def main():
    global MODEL
    parser=argparse.ArgumentParser();parser.add_argument('--event',default='Thanksgiving potluck');parser.add_argument('--model',choices=['qwen3:4b','qwen3:14b'],default='qwen3:4b');args=parser.parse_args();MODEL=args.model
    audit=[]
    planning_schema={'type':'object','properties':{'queries':{'type':'array','maxItems':2,'items':{'type':'string'}}},'required':['queries'],'additionalProperties':False}
    plan=model_call([{'role':'system','content':'Suggest at most two short generic Amazon product searches for the occasion. Do not include names, addresses, dates or any personal information. Do not assume the user hosts the occasion. Return JSON.'},{'role':'user','content':args.event}],planning_schema,audit)
    evidence=[];seen=set()
    for query in plan['queries'][:2]:
        print('Trying Amazon search:',query,flush=True)
        search=read_amazon('https://www.amazon.com/s?'+urllib.parse.urlencode({'k':query[:160]}),audit)
        if search is None: break # Do not retry/challenge/bypass blocked Amazon requests.
        for asin in dict.fromkeys(re.findall(r'/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?"\s]|$)',search[0])):
            if asin in seen:continue
            seen.add(asin);url='https://www.amazon.com/dp/'+asin;page=read_amazon(url,audit)
            if page:evidence.append({'url':url,'title':'Amazon product '+asin,'text':page[1][:6000]})
            if len(seen)>=3:break
        if len(seen)>=3:break
    instruction=SYSTEM+' Return JSON matching the schema. Only retrieved product pages are evidence. If evidence is empty, should_recommend must be false, groups and recipes empty, and explain that Amazon access failed. Do not invent product details. Include useful questions to ask the user in missing_information.'
    result=model_call([{'role':'system','content':instruction},{'role':'user','content':json.dumps({'event':args.event,'budget_cents':8000,'role':'unknown','owned_items':'unknown','evidence':evidence})}],SCHEMA,audit)
    validated=validate_result(result,[{'url':x['url'],'title':x['title']} for x in evidence],8000,'live')
    if not evidence and (validated['items'] or validated['recipes'] or validated['should_recommend']):raise RuntimeError('Local model tried to recommend without product evidence')
    report={'provider':'ollama-local','model':MODEL,'event':args.event,'status':'researched' if evidence else 'blocked_by_amazon','observed_at':datetime.now(timezone.utc).isoformat(),'api_cost_usd':0,'cost_note':'Excludes local hardware, electricity and internet. No cloud API was called.','result':validated,'audit':audit,'evidence':evidence}
    path=ROOT/'.local/qwen-potluck-test.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(report,indent=2));path.chmod(0o600)
    print(json.dumps({'status':report['status'],'summary':validated['summary'],'items':len(validated['items']),'api_cost_usd':0,'model_calls':len([a for a in audit if a['type']=='local_model']),'report':str(path)},indent=2))

if __name__=='__main__':main()
