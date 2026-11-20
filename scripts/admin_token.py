"""Display your local admin token only when explicitly run in your terminal."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tokensand.agent_api import ensure_admin_token
print(ensure_admin_token())
