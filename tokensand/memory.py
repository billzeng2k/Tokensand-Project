import asyncio
import json
import sys
from .config import ROOT
DATASET = 'tokensand_demo_wardrobe'

async def seed():
    import cognee
    fixture = json.loads((ROOT / 'fixtures/shopping.json').read_text())
    await cognee.remember(fixture['memory'], dataset_name=DATASET)
    print('Stored synthetic wardrobe preferences in local Cognee.')

async def recall():
    import cognee
    results = await cognee.recall('What jacket materials does the demo user prefer or reject?', datasets=[DATASET])
    if not results:
        raise RuntimeError('No Cognee memory found. Run npm run memory:seed first.')
    return json.dumps(results, default=str)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'seed':
        asyncio.run(seed())
    else:
        print(asyncio.run(recall()))
