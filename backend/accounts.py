"""Local accounts: salted scrypt passwords, opaque sessions and owner-scoped history."""
import hashlib
import secrets
import sqlite3
import time
from contextlib import contextmanager
from .config import ROOT

DB = ROOT / 'runtime/accounts.sqlite3'

@contextmanager
def connect():
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        with c:yield c
    finally:c.close()

def initialize():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS logins(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,user_id TEXT REFERENCES users(id),conversation TEXT,role TEXT,content TEXT,created REAL);
        CREATE INDEX IF NOT EXISTS messages_owner ON messages(user_id,id);
        ''')

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return salt + ':' + digest

def register(email,password):
    with connect() as c:
        uid=secrets.token_hex(16)
        try:c.execute('INSERT INTO users VALUES(?,?,?)',(uid,email,password_hash(password)))
        except sqlite3.IntegrityError:return None
        return {'id':uid,'email':email}

def login(email,password):
    with connect() as c:
        row=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
    expected=row['password'] if row else password_hash('dummy-password', '00'*16)
    actual=password_hash(password,expected.split(':')[0])
    if not row or not secrets.compare_digest(actual,expected):return None
    return {'id':row['id'],'email':row['email']}

def issue(uid):
    token=secrets.token_urlsafe(32)
    with connect() as c:
        c.execute('DELETE FROM logins WHERE expires<?',(time.time(),))
        c.execute('INSERT INTO logins VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,time.time()+86400))
    return token

def user(token):
    if not token:return None
    with connect() as c:
        row=c.execute('SELECT users.id,email FROM logins JOIN users ON users.id=logins.user_id WHERE token=? AND expires>?',
            (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
    return dict(row) if row else None

def revoke(token):
    with connect() as c:c.execute('DELETE FROM logins WHERE token=?',(hashlib.sha256((token or '').encode()).hexdigest(),))

def save(uid,conversation,text,response):
    with connect() as c:
        c.executemany('INSERT INTO messages(user_id,conversation,role,content,created) VALUES(?,?,?,?,?)',
          [(uid,conversation,role,content,time.time()) for role,content in [('user',text),('assistant',response)]])

def history(uid):
    with connect() as c:
        return [dict(r) for r in c.execute('SELECT conversation,role,content,created FROM (SELECT * FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 200) ORDER BY id',(uid,))]

def clear(uid):
    with connect() as c:c.execute('DELETE FROM messages WHERE user_id=?',(uid,))
