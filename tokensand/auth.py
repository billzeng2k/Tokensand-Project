"""Google server OAuth with browser-bound, single-use state and encrypted grants."""
from contextlib import contextmanager
from http.cookies import SimpleCookie
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import urllib.parse
import urllib.request
from cryptography.fernet import Fernet
from google.oauth2 import id_token
from google.auth.transport.requests import Request
from .config import LOCAL
from . import tenancy

DB = LOCAL / 'accounts.sqlite3'
CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar.readonly'
SESSION_SECONDS = 7 * 24 * 3600

@contextmanager
def db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, sub TEXT UNIQUE NOT NULL, email TEXT NOT NULL, name TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS oauth(state TEXT PRIMARY KEY, browser TEXT NOT NULL, purpose TEXT NOT NULL, user_id TEXT, verifier TEXT NOT NULL, nonce TEXT NOT NULL, expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS grants(user_id TEXT PRIMARY KEY, secret BLOB NOT NULL);
    ''')
    os.chmod(DB, 0o600)
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()

def client():
    path = LOCAL / 'google-web-client.json'
    value = json.loads(path.read_text()).get('web', {}) if path.exists() else {}
    return (os.getenv('GOOGLE_CLIENT_ID') or value.get('client_id'),
            os.getenv('GOOGLE_CLIENT_SECRET') or value.get('client_secret'))

def configured():
    return all(client())

def origin():
    value = os.getenv('UPNEXT_APP_URL', 'http://localhost:8787').rstrip('/')
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('Invalid application URL')
    if parsed.scheme != 'https' and parsed.hostname not in ('localhost', '127.0.0.1'):
        raise ValueError('HTTPS is required outside localhost')
    return value

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def cookie(handler, name):
    try:
        jar = SimpleCookie(handler.headers.get('Cookie', ''))
        return jar[name].value if name in jar else ''
    except Exception:
        return ''

def cookie_header(name, value, age):
    return f'{name}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={age}' + ('; Secure' if origin().startswith('https:') else '')

def user(handler):
    sid = cookie(handler, 'upnext_session')
    if not sid:
        return None
    with db() as c:
        row = c.execute('SELECT u.* FROM users u JOIN sessions s ON u.id=s.user_id WHERE s.id=? AND s.expires>?', (digest(sid), time.time())).fetchone()
    return dict(row) if row else None

def users():
    with db() as c:
        return [dict(r) for r in c.execute('SELECT id,email,name FROM users ORDER BY email')]

def cipher():
    key = os.getenv('UPNEXT_TOKEN_ENCRYPTION_KEY')
    if not key:
        path = LOCAL / 'token-encryption.key'
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(Fernet.generate_key())
        except FileExistsError:
            pass
        key = path.read_bytes()
    return Fernet(key)

def grant(uid):
    with db() as c:
        row = c.execute('SELECT secret FROM grants WHERE user_id=?', (uid,)).fetchone()
    return json.loads(cipher().decrypt(row[0])) if row else None

def connected(uid):
    with db() as c:
        return bool(c.execute('SELECT 1 FROM grants WHERE user_id=?', (uid,)).fetchone())

def save_grant(uid, token):
    encrypted = cipher().encrypt(json.dumps({'refresh_token': token}).encode())
    with db() as c:
        c.execute('INSERT OR REPLACE INTO grants VALUES(?,?)', (uid, encrypted))

def calendar_config(uid):
    value = grant(uid)
    if not value:
        raise ValueError('Connect Google Calendar in the app first.')
    client_id, secret = client()
    return {'calendarid': 'primary', 'credentials': {'auth_type': 'manual', 'client_id': client_id, 'client_secret': secret, 'refresh_token': value['refresh_token']}}

def disconnect(uid):
    # Serialize against sync so an in-flight connector cannot restore a deleted snapshot.
    from .calendar import SYNC_LOCK
    with SYNC_LOCK:
        with db() as c:
            c.execute('DELETE FROM grants WHERE user_id=?', (uid,))
        (tenancy.directory() / 'calendar-events.json').unlink(missing_ok=True)

def redirect(handler, url, cookies=()):
    handler.send_response(303)
    handler.send_header('Location', url)
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Referrer-Policy', 'no-referrer')
    for value in cookies:
        handler.send_header('Set-Cookie', value)
    handler.end_headers()

def start(handler, purpose):
    if not configured():
        return handler.send({'error': 'Google sign-in is not configured by the app owner yet.'}, 503)
    account = user(handler)
    if purpose == 'calendar' and not account:
        return handler.send({'error': 'Sign in first.'}, 401)
    state, browser, verifier, nonce = [secrets.token_urlsafe(32) for _ in range(4)]
    with db() as c:
        c.execute('DELETE FROM oauth WHERE expires<?', (time.time(),))
        c.execute('INSERT INTO oauth VALUES(?,?,?,?,?,?,?)', (digest(state), digest(browser), purpose, account['id'] if account else None, verifier, nonce, time.time()+600))
    params = {'client_id': client()[0], 'redirect_uri': origin()+'/auth/google/callback', 'response_type': 'code',
              'scope': 'openid email profile' + (' '+CALENDAR_SCOPE if purpose == 'calendar' else ''),
              'state': state, 'nonce': nonce, 'code_challenge_method': 'S256',
              'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),
              'prompt': 'consent' if purpose == 'calendar' else 'select_account'}
    if purpose == 'calendar':
        params.update(access_type='offline', login_hint=account['email'])
    redirect(handler, 'https://accounts.google.com/o/oauth2/v2/auth?'+urllib.parse.urlencode(params), [cookie_header('upnext_oauth', browser, 600)])

def exchange(code, verifier):
    payload = {'client_id': client()[0], 'client_secret': client()[1], 'code': code, 'code_verifier': verifier,
               'grant_type': 'authorization_code', 'redirect_uri': origin()+'/auth/google/callback'}
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=urllib.parse.urlencode(payload).encode(), headers={'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

def verify(token, nonce):
    claims = id_token.verify_oauth2_token(token, Request(), client()[0])
    if not claims.get('sub') or not claims.get('email_verified') or not hmac.compare_digest(claims.get('nonce', ''), nonce):
        raise ValueError('Invalid Google identity')
    if claims.get('azp', client()[0]) != client()[0]:
        raise ValueError('Invalid authorized party')
    return claims

def callback(handler):
    query = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    state = query.get('state', [''])[0]
    try:
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM oauth WHERE state=?', (digest(state),)).fetchone()
            if not row or row['expires'] < time.time() or not hmac.compare_digest(row['browser'], digest(cookie(handler, 'upnext_oauth'))):
                raise ValueError('Invalid OAuth state')
            c.execute('DELETE FROM oauth WHERE state=?', (digest(state),))
        if 'error' in query:
            raise ValueError('Consent declined')
        tokens = exchange(query['code'][0], row['verifier'])
        claims = verify(tokens['id_token'], row['nonce'])
        uid = digest('google:'+claims['sub'])
        if row['purpose'] == 'calendar':
            account = user(handler)
            if not account or account['id'] != row['user_id'] or uid != account['id']:
                raise ValueError('Calendar account must match signed-in account')
            if CALENDAR_SCOPE not in tokens.get('scope', '').split():
                raise ValueError('Calendar permission missing')
            previous = grant(uid)
            refresh = tokens.get('refresh_token') or (previous or {}).get('refresh_token')
            if not refresh:
                raise ValueError('Offline access missing')
            save_grant(uid, refresh)
            redirect(handler, '/?connection=calendar', [cookie_header('upnext_oauth', '', 0)])
        else:
            sid = secrets.token_urlsafe(32)
            with db() as c:
                c.execute('INSERT INTO users VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET email=excluded.email,name=excluded.name', (uid, claims['sub'], claims['email'], claims.get('name', '')))
                c.execute('DELETE FROM sessions WHERE expires<? OR id=?', (time.time(), digest(cookie(handler, 'upnext_session'))))
                c.execute('INSERT INTO sessions VALUES(?,?,?)', (digest(sid), uid, time.time()+SESSION_SECONDS))
            redirect(handler, '/', [cookie_header('upnext_session', sid, SESSION_SECONDS), cookie_header('upnext_oauth', '', 0)])
    except Exception:
        # Never log codes, tokens, identity claims, or upstream response bodies.
        redirect(handler, '/?connection=failed', [cookie_header('upnext_oauth', '', 0)])

def logout(handler):
    with db() as c:
        c.execute('DELETE FROM sessions WHERE id=?', (digest(cookie(handler, 'upnext_session')),))
    handler.send_response(200)
    handler.send_header('Set-Cookie', cookie_header('upnext_session', '', 0))
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Cache-Control', 'no-store')
    handler.end_headers()
    handler.wfile.write(b'{"ok":true}')
