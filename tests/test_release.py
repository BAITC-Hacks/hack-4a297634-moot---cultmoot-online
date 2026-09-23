import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from backend import main as server, tutorials
from backend.router.state import Session
from backend.services import assistant
from backend.voice.realtime import proxy_voice
from tests.test_platform import PlatformTests


class ReleaseTests(PlatformTests):
    def test_contextual_assistant_skips_legacy_router(self):
        csrf = self.register()
        self.turn('привет', csrf)
        result = httpx.Response(200, request=httpx.Request('POST', 'https://api.openai.com/v1/responses'),
            json={'status': 'completed', 'output': [{'content': [{'type': 'output_text', 'text': 'С удовольствием помогу разобраться.'}]}]})
        with patch.object(server.settings, 'mode', 'assistant'), patch.object(server.http, 'post', new=AsyncMock(return_value=result)) as post, patch.object(server.engine, 'decide', side_effect=AssertionError('Legacy router used')):
            r = self.turn('Объясни простыми словами, что ты умеешь', csrf)
        self.assertEqual(r['response'], 'С удовольствием помогу разобраться.')
        self.assertFalse(r['backend']['bank_connected'])
        self.assertEqual(r['trace']['provider'], 'openai_assistant')
        payload = post.call_args.kwargs['json']
        self.assertEqual(len(payload['input']), 3)
        self.assertFalse(payload['store'])
        self.assertNotIn('SCENARIO_CATALOG', json.dumps(payload))

    def test_known_card_question_never_waits_for_model(self):
        csrf = self.register()
        with patch.object(server.settings, 'mode', 'assistant'), patch.object(server.http, 'post', side_effect=AssertionError('Unnecessary provider call')):
            r = self.turn('Потерял карту', csrf)
        self.assertEqual(r['trace']['provider'], 'local_reference')
        self.assertIn('не могу заблокировать', r['response'])

    def test_unsupported_guide_does_not_open_unrelated_slides(self):
        state = Session()
        self.assertIsNone(tutorials.handle('Где ближайший банкомат?', state))
        self.assertIsNone(state.tutorial_pending)
        tutorials.handle('Где найти переводы?', state)
        tutorials.handle('Да, пожалуйста', state)
        self.assertEqual(tutorials.view(state)['id'], 'transfer')
        state.language = 'mixed'
        self.assertEqual(tutorials.view(state)['language'], 'ru')
        self.assertEqual(tutorials.language('I lost my card'), 'other')
        self.assertEqual(tutorials.language('Пропала карта', 'other'), 'ru')

    def test_pcm_cache_and_mp3_are_not_confused(self):
        csrf = self.register()
        r = self.turn('привет', csrf)
        class Audio:
            status_code = 200
            async def aiter_bytes(self): yield b'\x00\x00' * 240
            async def aclose(self): pass
        with patch.object(server.http, 'send', new=AsyncMock(return_value=Audio())) as send:
            a = self.client.get(r['audio_url'] + '?format=pcm')
            self.assertEqual(a.status_code, 200)
            self.assertTrue(a.headers['content-type'].startswith('audio/pcm'))
            self.assertEqual(a.headers['x-accel-buffering'], 'no')
            self.client.get(r['audio_url'] + '?format=pcm')
            self.assertEqual(send.await_count, 1)
            self.client.get(r['audio_url'])
            self.assertEqual(send.await_count, 2)
            self.assertEqual(self.client.get(r['audio_url'] + '?format=invalid').status_code, 422)

    def test_tts_failure_releases_capacity_for_retry(self):
        csrf = self.register()
        r = self.turn('привет', csrf)
        with patch.object(server.http, 'send', new=AsyncMock(side_effect=httpx.ConnectTimeout('private-error'))):
            failed = self.client.get(r['audio_url'] + '?format=pcm')
        self.assertEqual(failed.status_code, 502)
        self.assertNotIn('private-error', failed.text)
        self.assertFalse(server.audio_slots.locked())
        s = server.store.get(self.client.cookies.get('vr_session'))
        self.assertFalse(s.audio_responses[r['trace']['request_id']]['generating'])

    def test_assistant_provider_error_is_sanitized(self):
        csrf = self.register()
        with patch.object(server.settings, 'mode', 'assistant'), patch.object(server.http, 'post', new=AsyncMock(side_effect=httpx.ConnectError('private-error'))):
            r = self.client.post('/api/route', json={'text': 'Расскажи о своих возможностях', 'request_id': '10000000-0000-4000-8000-000000000001'}, headers={'x-csrf-token': csrf})
        self.assertEqual(r.status_code, 502)
        self.assertNotIn('private-error', r.text)
        self.assertEqual(self.client.get('/api/history').json()['messages'], [])


class VoiceRelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_interruption_cancels_old_reply_and_empty_speech_recovers(self):
        queue = asyncio.Queue()
        received = asyncio.Queue()
        disconnected = asyncio.Event()
        started = asyncio.Event()
        cancelled = asyncio.Event()
        results = []
        class Upstream:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def send(self, data): pass
            def __aiter__(self): return self
            async def __anext__(self): return json.dumps(await queue.get())
        class Socket:
            query_params = {}
            async def accept(self): pass
            async def close(self, **kwargs): pass
            async def iter_bytes(self):
                await disconnected.wait()
                if False: yield b''
            async def send_json(self, data):
                results.append(data)
                await received.put(data)
        async def route(text, elapsed):
            if text == 'first':
                started.set()
                try: await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise
            return {'response': text}
        async def emit(kind, item='a', **kwargs):
            await queue.put({'type': kind, 'item_id': item, **kwargs})
        async def wait_for(kind):
            async with asyncio.timeout(2):
                while True:
                    event = await received.get()
                    if event['type'] == kind: return event
        settings = SimpleNamespace(openai_key='test', realtime_model='gpt-4o-transcribe', ttl=30, max_audio_seconds=45)
        state = Session()
        with patch('backend.voice.realtime.websockets.connect', return_value=Upstream()):
            task = asyncio.create_task(proxy_voice(Socket(), state, settings, route))
            try:
                await emit('session.updated')
                await wait_for('ready')
                await emit('input_audio_buffer.speech_started')
                await emit('input_audio_buffer.speech_stopped')
                await emit('conversation.item.input_audio_transcription.completed', transcript='first')
                await asyncio.wait_for(started.wait(), 2)
                await emit('input_audio_buffer.speech_started', 'b')
                await asyncio.wait_for(cancelled.wait(), 2)
                await emit('conversation.item.input_audio_transcription.completed', 'a', transcript='stale')
                await emit('input_audio_buffer.speech_stopped', 'b')
                await emit('conversation.item.input_audio_transcription.completed', 'b', transcript='second')
                self.assertEqual((await wait_for('result'))['data']['response'], 'second')
                await emit('input_audio_buffer.speech_started', 'c')
                await emit('input_audio_buffer.speech_stopped', 'c')
                await emit('conversation.item.input_audio_transcription.completed', 'c', transcript=' ')
                self.assertIn('Не расслышала', (await wait_for('error'))['message'])
                self.assertEqual(len([r for r in results if r['type'] == 'result']), 1)
            finally:
                disconnected.set()
                await asyncio.wait_for(task, 2)
        self.assertFalse(state.voice_active)


if __name__ == '__main__': unittest.main()
