"""Build an ignored, locally paired extension. Never commit the generated token."""
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tokensand.config import ROOT,LOCAL
from tokensand.amazon_bridge import token
out=LOCAL/'amazon-extension'
shutil.copytree(ROOT/'browser-extension',out,dirs_exist_ok=True)
(out/'config.js').write_text('const UPNEXT_BRIDGE_TOKEN = '+json.dumps(token())+';\n')
(out/'config.js').chmod(0o600)
print('Load unpacked in chrome://extensions: '+str(out))
