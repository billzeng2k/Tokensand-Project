"""Google Desktop OAuth using a loopback callback, state and PKCE; no credentials printed."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tokensand.calendar import CONFIG, LOCAL, private_json


def main():
    path = LOCAL / 'google-oauth-client.json'
    if not path.exists(): raise ValueError('Missing client file')
    path.chmod(0o600)
    client = json.loads(path.read_text())['installed']
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    result = {}
    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            valid = secrets.compare_digest(query.get('state', [''])[0], state)
            if valid: result.update(query)
            self.send_response(200 if valid else 400); self.end_headers()
            self.wfile.write(b'You can close this tab and return to Tokensand.' if valid else b'Invalid callback.')
    with HTTPServer(('127.0.0.1', 0), Callback) as server:
        redirect = f'http://127.0.0.1:{server.server_port}/'
        params = {'client_id': client['client_id'], 'redirect_uri': redirect, 'response_type': 'code',
                  'scope': 'https://www.googleapis.com/auth/calendar.readonly', 'access_type': 'offline',
                  'prompt': 'consent', 'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256'}
        url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params)
        print('Opening Google sign-in. This requests read-only Calendar access, not Gmail.')
        webbrowser.open(url)
        print('If no browser opened, visit this authorization URL on this machine:\n' + url, flush=True)
        server.timeout = 180
        server.handle_request()
    if not result.get('code'): raise ValueError('No authorization code')
    data = urllib.parse.urlencode({'client_id': client['client_id'], 'client_secret': client['client_secret'],
                                  'code': result['code'][0], 'grant_type': 'authorization_code',
                                  'redirect_uri': redirect, 'code_verifier': verifier}).encode()
    with urllib.request.urlopen('https://oauth2.googleapis.com/token', data=data, timeout=30) as response:
        token = json.load(response)
    config = {'calendarid': 'primary', 'credentials': {'auth_type': 'manual', 'client_id': client['client_id'],
              'client_secret': client['client_secret'], 'refresh_token': token['refresh_token']}}
    private_json(CONFIG, config)
    print('Google Calendar connected. Run npm run calendar:sync, then open the app. Token saved locally only.')

if __name__ == '__main__':
    try: main()
    except Exception: raise SystemExit('Connection was not completed. See docs/AIRBYTE.md and retry. Credentials were not printed.')
