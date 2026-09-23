"""Opt-in live OpenAI smoke test. Sends only a fixed, synthetic greeting.

No customer database, conversation history, routing catalog or secrets are printed.
The API key is read locally and used only as the OpenAI Authorization header.
"""
import asyncio
import base64
import json
import sys
import time
import wave
from pathlib import Path
import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import settings
from backend.voice.realtime import session_config

TEXT = 'Здравствуйте! Я рядом. Давайте разберёмся вместе, шаг за шагом.'


async def main():
    if not settings.openai_key:
        raise SystemExit('OpenAI is not configured')
    headers = {'Authorization': 'Bearer ' + settings.openai_key}
    pcm = bytearray()
    started = time.perf_counter()
    first_ms = None
    async with httpx.AsyncClient(timeout=20) as client:
        async with client.stream('POST', 'https://api.openai.com/v1/audio/speech', headers=headers,
                json={'model': settings.tts_model, 'voice': settings.voice,
                      'input': TEXT, 'response_format': 'pcm'}) as response:
            if response.status_code != 200:
                raise SystemExit(f'TTS failed: HTTP {response.status_code}')
            async for chunk in response.aiter_bytes():
                if chunk and first_ms is None:
                    first_ms = round((time.perf_counter() - started) * 1000)
                pcm.extend(chunk)
        if len(pcm) < 4800 or len(pcm) % 2:
            raise SystemExit('Invalid PCM response')
        print(json.dumps({'tts': 'ok', 'voice': settings.voice, 'first_chunk_ms': first_ms,
                          'audio_seconds': round(len(pcm) / 48000, 2)}), flush=True)
        response = await client.post('https://api.openai.com/v1/responses', headers=headers,
            json={'model': settings.assistant_model, 'input': 'Say a short greeting in Russian.',
                  'max_output_tokens': 80, 'store': False})
        if response.status_code != 200 or response.json().get('status') != 'completed':
            raise SystemExit(f'Assistant model failed: HTTP {response.status_code}')
        print(json.dumps({'assistant_model': settings.assistant_model, 'status': 'ok'}), flush=True)
    async with websockets.connect('wss://api.openai.com/v1/realtime?intent=transcription',
            additional_headers=headers, open_timeout=15, max_size=1048576) as ws:
        config = session_config(settings)
        config['audio']['input']['transcription'].pop('prompt', None)
        await ws.send(json.dumps({'type': 'session.update', 'session': config}))
        async with asyncio.timeout(15):
            while True:
                event = json.loads(await ws.recv())
                if event.get('type') == 'session.updated': break
                if event.get('type') == 'error': raise SystemExit('Realtime configuration rejected')
        async def feed():
            payload = bytes(pcm) + b'\0' * 48000
            for i in range(0, len(payload), 2400):
                await ws.send(json.dumps({'type': 'input_audio_buffer.append',
                    'audio': base64.b64encode(payload[i:i+2400]).decode()}))
                await asyncio.sleep(.05)
        sender = asyncio.create_task(feed())
        try:
            async with asyncio.timeout(30):
                while True:
                    event = json.loads(await ws.recv())
                    if event.get('type') == 'conversation.item.input_audio_transcription.completed':
                        transcript = event.get('transcript', '')
                        if 'шаг' not in transcript.lower(): raise SystemExit('Synthetic speech was not recognized as expected')
                        print(json.dumps({'recognition': 'ok', 'language': 'ru', 'synthetic_transcript': transcript}, ensure_ascii=True), flush=True)
                        break
                    if event.get('type') in {'error', 'conversation.item.input_audio_transcription.failed'}:
                        raise SystemExit('Synthetic speech recognition failed')
        finally:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
    if '--save-sample' in sys.argv:
        target = ROOT / 'reports' / 'voice-marin-ru.wav'
        target.parent.mkdir(exist_ok=True)
        with wave.open(str(target), 'wb') as out:
            out.setnchannels(1); out.setsampwidth(2); out.setframerate(24000); out.writeframes(pcm)
        print('Synthetic voice sample saved to reports/voice-marin-ru.wav')


if __name__ == '__main__':
    try: asyncio.run(main())
    except Exception as exc: raise SystemExit('Speech check failed: ' + type(exc).__name__) from None
