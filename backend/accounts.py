"""Local accounts: salted scrypt passwords, opaque sessions and owner-scoped history."""
import hashlib
import secrets
import sqlite3
import time
from contextlib import contextmanager
from cryptography.fernet import Fernet
from .config import ROOT

DB = ROOT / 'runtime/accounts.sqlite3'

def cipher():
    key_path=DB.parent/'history.key'
    try:key=key_path.read_bytes()
    except FileNotFoundError:
        key=Fernet.generate_key()
        try:
            with key_path.open('xb') as f:f.write(key)
        except FileExistsError:key=key_path.read_bytes()
    return Fernet(key)

def encrypt(text):return 'enc:'+cipher().encrypt(text.encode('utf-8')).decode('ascii')
def decrypt(text):return cipher().decrypt(text[4:].encode('ascii')).decode('utf-8') if text.startswith('enc:') else text

@contextmanager
def connect():
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA secure_delete=ON')
    try:
        with c:yield c
    finally:c.close()

def initialize():
    with connect() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA secure_delete=ON;
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS logins(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,user_id TEXT REFERENCES users(id),conversation TEXT,role TEXT,content TEXT,created REAL);
        CREATE INDEX IF NOT EXISTS messages_owner ON messages(user_id,id);
        CREATE TABLE IF NOT EXISTS auth_attempts(bucket TEXT PRIMARY KEY,count INTEGER,expires REAL);
        CREATE TABLE IF NOT EXISTS metadata(name TEXT PRIMARY KEY,value TEXT);
        ''')
        migrated=c.execute("SELECT 1 FROM metadata WHERE name='encrypted_history'").fetchone()
        if migrated and not (DB.parent/'history.key').exists() and c.execute('SELECT 1 FROM messages LIMIT 1').fetchone():
            raise RuntimeError('Missing history encryption key. Restore runtime/history.key from backup.')
        if not migrated:
            for row in c.execute('SELECT id,content FROM messages').fetchall():
                c.execute('UPDATE messages SET content=? WHERE id=?',(encrypt(row['content']),row['id']))
            c.execute("INSERT INTO metadata VALUES('encrypted_history','1')")
    with connect() as c:c.execute('PRAGMA wal_checkpoint(TRUNCATE)')

def password_hash(password, salt=None, legacy=False):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384 if legacy else 32768,r=8,p=1 if legacy else 3,maxmem=64*1024*1024).hex()
    return ('' if legacy else 's2:')+salt + ':' + digest

DUMMY_HASH=password_hash('nonexistent-account-password','00'*16)

def allow_auth(email,ip):
    now=time.time()
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('DELETE FROM auth_attempts WHERE expires<?',(now,))
        buckets=[(hashlib.sha256((kind+value).encode()).hexdigest(),limit) for kind,value,limit in [('email:',email,20),('ip:',ip,100)]]
        for bucket,limit in buckets:
            row=c.execute('SELECT count FROM auth_attempts WHERE bucket=?',(bucket,)).fetchone()
            if row and row['count']>=limit:return False
        for bucket,_ in buckets:
            c.execute('INSERT INTO auth_attempts VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1',(bucket,now+900))
    return True

def register(email,password):
    with connect() as c:
        uid=secrets.token_hex(16)
        try:c.execute('INSERT INTO users VALUES(?,?,?)',(uid,email,password_hash(password)))
        except sqlite3.IntegrityError:return None
        return {'id':uid,'email':email}

def login(email,password):
    with connect() as c:
        row=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
    expected=row['password'] if row else DUMMY_HASH
    legacy=not expected.startswith('s2:')
    actual=password_hash(password,expected.split(':')[-2],legacy=legacy)
    if not row or not secrets.compare_digest(actual,expected):return None
    if legacy:
        upgraded=password_hash(password)
        with connect() as c:c.execute('UPDATE users SET password=? WHERE id=?',(upgraded,row['id']))
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

def revoke_all(uid):
    with connect() as c:c.execute('DELETE FROM logins WHERE user_id=?',(uid,))

def change_password(uid,password):
    hashed=password_hash(password)
    with connect() as c:
        c.execute('UPDATE users SET password=? WHERE id=?',(hashed,uid))
        c.execute('DELETE FROM logins WHERE user_id=?',(uid,))

def save(uid,conversation,text,response):
    with connect() as c:
        c.executemany('INSERT INTO messages(user_id,conversation,role,content,created) VALUES(?,?,?,?,?)',
          [(uid,conversation,role,encrypt(content),time.time()) for role,content in [('user',text),('assistant',response)]])
        c.execute('DELETE FROM messages WHERE user_id=? AND id NOT IN (SELECT id FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 2000)',(uid,uid))

def history(uid):
    with connect() as c:
        return [dict(r)|{'content':decrypt(r['content'])} for r in c.execute('SELECT conversation,role,content,created FROM (SELECT * FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 200) ORDER BY id',(uid,))]

def clear(uid):
    with connect() as c:c.execute('DELETE FROM messages WHERE user_id=?',(uid,))
    with connect() as c:c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
