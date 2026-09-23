import unittest
from unittest.mock import patch,Mock
from tests import test_upgrade
from backend import accounts,tutorials
from backend import main as server
from backend.router.state import Session
from backend.router.validator import safe_decision
from backend.voice.realtime import session_config

class PlatformTests(test_upgrade.UpgradeTests):
    def test_password_change_revokes_old_sessions(self):
        csrf=self.register();old_cookie=self.client.cookies.get('vr_auth')
        r=self.client.post('/api/account/password',json={'current_password':'test-pass-12345','new_password':'new-password-67890'},headers={'x-csrf-token':csrf})
        self.assertEqual(r.status_code,200,r.text);self.assertIsNone(accounts.user(old_cookie))
        self.assertIsNone(accounts.login('one@gmail.com','test-pass-12345'))
        self.assertIsNotNone(accounts.login('one@gmail.com','new-password-67890'))
        self.assertEqual(self.client.get('/api/me').status_code,200)
    def test_wrong_password_cannot_change_account(self):
        csrf=self.register()
        r=self.client.post('/api/account/password',json={'current_password':'incorrect-password','new_password':'new-password-67890'},headers={'x-csrf-token':csrf})
        self.assertEqual(r.status_code,400)
        self.assertIsNotNone(accounts.login('one@gmail.com','test-pass-12345'))
    def test_logout_all_revokes_other_devices(self):
        csrf=self.register();u=self.client.get('/api/me').json()['user'];other=accounts.issue(u['id'])
        self.client.post('/api/account/logout-all',json={},headers={'x-csrf-token':csrf})
        self.assertIsNone(accounts.user(other));self.assertEqual(self.client.get('/api/me').status_code,401)
    def test_assistant_mode_never_executes_mock_operations(self):
        state=Session();scenario=next(s for s in server.catalog.scenarios if s.required_slots)
        d=safe_decision(server.catalog).model_copy(update={'decision':'route','scenario_id':scenario.id,'action':'ask_slot'})
        with patch.object(server.settings,'mode','assistant'),patch.object(server.engine.backend,'execute',side_effect=AssertionError('No mock execution')):
            d,response,details=server.engine.respond('Проверь мой баланс',d,state)
        self.assertFalse(details['bank_connected']);self.assertTrue(details['read_only'])
        self.assertNotIn('DEMO-',response);self.assertIsNone(state.awaiting_slot)
    def test_english_guide_and_manual_pause(self):
        state=Session();offer=tutorials.handle('Where can I find transfers?',state)
        self.assertIn('step by step',offer);tutorials.handle('yes',state)
        self.assertEqual(tutorials.view(state)['language'],'en')
        self.assertEqual(session_config(server.settings,'en','5')['audio']['input']['turn_detection']['silence_duration_ms'],5000)

if __name__=='__main__':unittest.main()
