"""Run the app's local research provider independently; no paid APIs."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tokensand import local_qwen
from tokensand.agent import validate_result
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--event',default='Thanksgiving potluck');parser.add_argument('--model',choices=local_qwen.MODELS,default='qwen3:14b');args=parser.parse_args()
    # CLI has no shared app queue; use its bounded direct HTTP transport.
    os.environ['AMAZON_RETRIEVAL']='http'
    audit=[]
    def call(messages,schema,name):
        start=time.monotonic();result,usage=local_qwen.model_call(messages,schema,args.model)
        audit.append({'type':'local_model','name':name,'model':args.model,'duration_seconds':round(time.monotonic()-start,2),**usage,'output':result,'api_cost_usd':0});return result
    status='researched';result=None
    try:
        answer,evidence=local_qwen.research(args.event,{'event':{'title':args.event},'budget_cents':8000,'preferences':'Unknown; ask rather than assume'},call,audit)
        result=validate_result(answer,[{'url':e['url'],'title':e['title']} for e in evidence],8000,'live')
    except RuntimeError as exc:
        if str(exc)!='amazon_evidence_unavailable':raise
        status='blocked_by_amazon';evidence=[]
    report={'provider':'ollama-local','model':args.model,'status':status,'observed_at':datetime.now(timezone.utc).isoformat(),'api_cost_usd':0,'event':args.event,'result':result,'audit':audit,'evidence':evidence}
    path=ROOT/'.local'/('qwen-potluck-'+args.model.split(':')[-1]+'.json');path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(report,indent=2));path.chmod(0o600)
    print(json.dumps({'status':status,'model':args.model,'items':len(result['items']) if result else 0,'api_cost_usd':0,'report':str(path)},indent=2))
if __name__=='__main__':main()
