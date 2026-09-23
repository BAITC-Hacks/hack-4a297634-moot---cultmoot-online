import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from backend import accounts
from backend.main import app
from backend.router.state import Session
from backend import tutorials

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=accounts.DB
        accounts.DB=Path(self.tmp.name)/'test.sqlite3'
        self.client=TestClient(app);self.client.__enter__()
    def tearDown(self):
        self.client.__exit__(None,None,None);accounts.DB=self.old;self.tmp.cleanup()
    def register(self,email='one@gmail.com'):
        r=self.client.post('/api/auth/register',json={'email':email,'password':'test-pass-12345'})
        self.assertEqual(r.status_code,200,r.text)
        return self.client.post('/api/session',json={}).json()['csrf']
    def turn(self,text,csrf):
        r=self.client.post('/api/route',json={'text':text,'request_id':str(uuid4())},headers={'x-csrf-token':csrf})
        self.assertEqual(r.status_code,200,r.text);return r.json()
    def test_auth_csrf_ownership_and_logout(self):
        self.assertEqual(self.client.get('/api/history').status_code,401)
        csrf=self.register();self.turn('привет',csrf)
        self.assertEqual(len(self.client.get('/api/history').json()['messages']),2)
        self.assertEqual(self.client.delete('/api/history').status_code,403)
        old_cookie=self.client.cookies.get('vr_auth')
        self.assertEqual(self.client.post('/api/logout',json={},headers={'x-csrf-token':csrf}).status_code,200)
        self.assertIsNone(accounts.user(old_cookie))
        self.register('two@gmail.com')
        self.assertEqual(self.client.get('/api/history').json()['messages'],[])
    def test_guide_consent_steps_and_history_delete(self):
        csrf=self.register();offer=self.turn('Где найти перевод по телефону?',csrf)
        self.assertTrue(offer['tutorial_offer']);self.assertIsNone(offer['tutorial'])
        accepted=self.turn('да',csrf);self.assertEqual(accepted['tutorial']['id'],'transfer')
        step=self.turn('дальше',csrf);self.assertEqual(step['tutorial']['index'],1)
        self.client.delete('/api/history',headers={'x-csrf-token':csrf})
        self.assertEqual(self.client.get('/api/history').json()['messages'],[])
    def test_kazakh_and_password_storage(self):
        s=Session();tutorials.handle('Аударымды қайдан табамын?',s)
        self.assertEqual(s.language,'kk');self.assertEqual(s.tutorial_pending,'transfer')
        tutorials.handle('иә',s);self.assertIsNotNone(tutorials.view(s))
        self.register()
        with accounts.connect() as c:stored=c.execute('SELECT password FROM users').fetchone()[0]
        self.assertNotIn('test-pass',stored)
        self.assertIsNone(accounts.login('one@gmail.com','wrong-password'))
    def test_origin_and_body_limits(self):
        self.assertEqual(self.client.post('/api/auth/login',json={},headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/auth/login',content='x'*17000,headers={'Content-Type':'application/json'}).status_code,413)

if __name__=='__main__':unittest.main()
