"""Server-selected account scope. Never derive this from shopper request parameters."""
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
import re
from .config import LOCAL

USER = ContextVar('upnext_user', default=None)

def directory():
    uid = USER.get()
    if uid is None:
        return LOCAL
    if not re.fullmatch(r'[a-f0-9]{64}', uid):
        raise ValueError('Invalid account scope')
    path = LOCAL / 'users' / uid
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path

@contextmanager
def scope(uid):
    token = USER.set(uid)
    try:
        directory()
        yield
    finally:
        USER.reset(token)

def enqueue(pool, fn, *args):
    return pool.submit(copy_context().run, fn, *args)
