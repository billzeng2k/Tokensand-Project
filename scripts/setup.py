"""Create local configuration without overwriting secrets or existing databases."""
import os
from pathlib import Path
import secrets
root = Path(__file__).resolve().parents[1]
path = root / '.env'
if not path.exists():
    text = (root / '.env.example').read_text().replace('SINGLESTORE_ROOT_PASSWORD=\n', f'SINGLESTORE_ROOT_PASSWORD={secrets.token_hex(24)}\n')
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(text)
    print('Created private .env with a random database password.')
else:
    print('Preserved existing .env.')
(root / '.local').mkdir(exist_ok=True)
print('Next: docker compose up -d; uv venv --python 3.12; uv pip sync requirements.lock')
