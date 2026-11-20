import os
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]
if os.getenv('TOKENSAND_NO_DOTENV') != '1':
    load_dotenv(ROOT / '.env', override=False)
LOCAL = ROOT / '.local'
if os.getenv('TOKENSAND_NO_DOTENV') != '1':
    LOCAL.mkdir(exist_ok=True)
# Confine Cognee state and model downloads to this checkout.
os.environ.setdefault('DATA_ROOT_DIRECTORY', str(LOCAL / 'cognee/data'))
os.environ.setdefault('SYSTEM_ROOT_DIRECTORY', str(LOCAL / 'cognee/system'))
os.environ.setdefault('HF_HOME', str(LOCAL / 'models'))
os.environ.setdefault('TELEMETRY_DISABLED', '1')
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

os.environ.setdefault('COGNEE_LOGS_DIR', str(LOCAL / 'cognee/logs'))
