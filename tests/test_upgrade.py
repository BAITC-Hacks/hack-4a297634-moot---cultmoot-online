import tempfile
import unittest
import asyncio
import time
from unittest.mock import AsyncMock,patch
from types import SimpleNamespace
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from backend import accounts
from backend.main import app
from backend.router.state import Session
from backend import tutorials
from backend import main as server
from backend.router.engine import Engine
from backend.security.rate_limit import RateLimiter
from backend.providers.openai_provider import OpenAIRouterProvider
from backend.router.schema import COMPACT_SCHEMA

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        server.rates.events.clear()
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

    def test_encrypted_history_and_clear_cached_traces(self):
        csrf=self.register();r=self.turn('привет',csrf)
        with accounts.connect() as c:
            encrypted=c.execute('SELECT content FROM messages LIMIT 1').fetchone()[0]
        self.assertTrue(encrypted.startswith('enc:'));self.assertNotIn('привет',encrypted)
        self.assertEqual(self.client.get('/api/history').json()['messages'][0]['content'],'привет')
        self.client.delete('/api/history',headers={'x-csrf-token':csrf})
        self.assertEqual(self.client.get('/api/trace/'+r['trace']['request_id']).status_code,404)
        self.assertEqual(self.client.get(r['audio_url']).status_code,404)

    def test_password_not_echoed_and_api_schema_hidden(self):
        r=self.client.post('/api/auth/register',json={'email':'x','password':'secret'})
        self.assertEqual(r.status_code,422);self.assertNotIn('secret',r.text)
        self.assertEqual(self.client.get('/openapi.json').status_code,404)
        self.assertEqual(self.client.post('/api/realtime/token',json={}).status_code,410)

    def test_auth_quota_persists_and_legacy_hash_upgrades(self):
        for _ in range(20):self.assertTrue(accounts.allow_auth('target@gmail.com','127.0.0.1'))
        self.assertFalse(accounts.allow_auth('target@gmail.com','different-ip'))
        self.register()
        legacy=accounts.password_hash('test-pass-12345',legacy=True)
        with accounts.connect() as c:c.execute('UPDATE users SET password=?',(legacy,))
        self.assertIsNotNone(accounts.login('one@gmail.com','test-pass-12345'))
        with accounts.connect() as c:self.assertTrue(c.execute('SELECT password FROM users').fetchone()[0].startswith('s2:'))

    def test_audio_cache_avoids_second_provider_request(self):
        csrf=self.register();r=self.turn('привет',csrf)
        class Audio:
            status_code=200
            async def aiter_bytes(self):yield b'ID3-test-audio'
            async def aclose(self):pass
        with patch.object(server.http,'send',new=AsyncMock(return_value=Audio())) as send:
            self.assertEqual(self.client.get(r['audio_url']).content,b'ID3-test-audio')
            self.assertEqual(self.client.get(r['audio_url']).content,b'ID3-test-audio')
            self.assertEqual(send.await_count,1)

    def test_foreign_audio_and_trace_denied(self):
        csrf=self.register();r=self.turn('привет',csrf)
        self.client.post('/api/logout',json={},headers={'x-csrf-token':csrf})
        self.register('other@gmail.com')
        self.assertEqual(self.client.get(r['audio_url']).status_code,404)
        self.assertEqual(self.client.get('/api/trace/'+r['trace']['request_id']).status_code,404)

    def test_host_and_cross_site_protection(self):
        self.assertEqual(self.client.get('/api/me',headers={'Host':'attacker.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/me',headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)
        self.assertEqual(self.client.get('/').headers['cross-origin-resource-policy'],'same-origin')

    def test_router_deadline_is_total_and_does_not_retry(self):
        async def slow(*args):await asyncio.sleep(1)
        provider=SimpleNamespace(route=AsyncMock(side_effect=slow))
        e=Engine(server.catalog,{'openai':provider},None,None,SimpleNamespace(router_deadline=.02))
        start=time.monotonic();d,a=asyncio.run(e.decide('test',Session()))
        self.assertLess(time.monotonic()-start,.5)
        self.assertEqual(d.decision,'clarify');self.assertEqual(a['errors'],['router_deadline'])
        self.assertEqual(provider.route.await_count,1)

    def test_limits_do_not_reset_when_windows_differ(self):
        r=RateLimiter();self.assertEqual(r.check('account',1,900),0)
        r.check('other',1,60)
        self.assertGreater(r.check('account',1,900),0)

    def test_compact_response_restores_server_derived_fields(self):
        import json
        compact={'decision':'clarify','scenario_id':None,'confidence':0.2,'reason_short':'Ambiguous',
          'alternatives':[],'language':'ru','pending_scenario_ids':[],'extracted_slots':[],
          'action':'ask_clarification','clarifying_question':'Уточните вопрос?','context_sufficient':False}
        provider=OpenAIRouterProvider(None,'test','test','https://example.invalid')
        provider.request=AsyncMock(return_value={'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(compact)}]}]})
        d,_=asyncio.run(provider.route('test',{'state':Session().context(),'transcript':'test'}))
        self.assertFalse(d.requires_confirmation);self.assertEqual(d.confirmation,'none')
        self.assertEqual(d.response_mode,'template');self.assertEqual(len(COMPACT_SCHEMA['properties']),11)

    def test_missing_encryption_key_fails_closed(self):
        csrf=self.register();self.turn('привет',csrf)
        key=accounts.DB.parent/'history.key';original=key.read_bytes();key.unlink()
        try:
            with self.assertRaises(RuntimeError):accounts.initialize()
            self.assertFalse(key.exists())
        finally:key.write_bytes(original)

    def test_exact_catalog_route_skips_model_but_context_does_not(self):
        import re
        provider=SimpleNamespace(route=AsyncMock(side_effect=RuntimeError('model should not run')))
        e=Engine(server.catalog,{'openai':provider},None,None,SimpleNamespace(router_deadline=.1))
        candidates=[(text,item) for text,item in e.exact_examples.items() if item and not re.search(r'\d',text) and server.catalog.by_id[item[0]].required_slots]
        text,(sid,_)=candidates[0]
        start=time.monotonic();d,a=asyncio.run(e.decide(text,Session()))
        self.assertEqual(d.scenario_id,sid);self.assertEqual(d.action,'ask_slot')
        self.assertEqual(a['attempts'],0);self.assertLess(time.monotonic()-start,.1)
        provider.route.assert_not_awaited()

if __name__=='__main__':unittest.main()
