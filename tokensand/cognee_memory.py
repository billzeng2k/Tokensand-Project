"""Account-isolated local Cognee session memory; SQLite remains canonical."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from . import tenancy


def recall(snapshot,event_id=None):
    root=(tenancy.directory()/'cognee-shopping'/hashlib.sha256((event_id or 'general').encode()).hexdigest()).resolve()
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    env=os.environ.copy()
    env.update(DATA_ROOT_DIRECTORY=str(root/'store'/'data'),SYSTEM_ROOT_DIRECTORY=str(root/'store'/'system'),
               COGNEE_LOGS_DIR=str(root/'logs'),CACHING='true',CACHE_BACKEND='sqlite',IMPROVE_AUTO_ENABLED='false',
               TELEMETRY_DISABLED='1',LLM_PROVIDER='ollama',LLM_MODEL='qwen3:14b',
               LLM_ENDPOINT='http://127.0.0.1:11434/v1',LLM_API_KEY='local')
    process=subprocess.run([sys.executable,'-m','tokensand.cognee_memory','worker',str(root)],input=json.dumps(snapshot),text=True,capture_output=True,env=env,timeout=90)
    if process.returncode:raise RuntimeError('cognee_memory_unavailable')
    line=next((line for line in reversed(process.stdout.splitlines()) if line.startswith('UPNEXT_MEMORY=')),None)
    if not line:raise RuntimeError('cognee_memory_unavailable')
    result=json.loads(line.split('=',1)[1])
    if result!=snapshot:raise RuntimeError('cognee_memory_snapshot_mismatch')
    return result


async def worker(root):
    import shutil
    snapshot=json.load(sys.stdin)
    encoded=json.dumps(snapshot,sort_keys=True)
    digest=hashlib.sha256(encoded.encode()).hexdigest()
    marker=root/'revision'
    rebuild=not marker.exists() or marker.read_text()!=digest
    # Rebuild only derived Cognee memory when a purchase/undo/forget changes source data.
    # This removes old remembered preferences rather than retrieving stale revisions.
    if rebuild and (root/'store').exists():shutil.rmtree(root/'store')
    import cognee
    from cognee.memory.entries import QAEntry
    if rebuild:
        await cognee.remember(QAEntry(question='shopping preferences purchases dismissals',answer=encoded),dataset_name='upnext_shopping',session_id='shopping',self_improvement=False)
        marker.write_text(digest)
    results=await cognee.recall('shopping preferences purchases dismissals',session_id='shopping',scope='session',top_k=1)
    if not results:raise RuntimeError('cognee_memory_empty')
    print('UPNEXT_MEMORY='+json.dumps(json.loads(results[0].answer)))


if __name__=='__main__':
    import asyncio
    asyncio.run(worker(Path(sys.argv[2])))
