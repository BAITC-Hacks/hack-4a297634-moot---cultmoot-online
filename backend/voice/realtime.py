import asyncio
import base64
import json
import time
import websockets
from fastapi import WebSocket


def session_config(settings, language='auto', pause='auto'):
    audio = {'format': {'type': 'audio/pcm', 'rate': 24000},
             'transcription': {'model': settings.realtime_model,
                 'prompt': 'Conversation in Russian, Kazakh or English, sometimes mixed. Halyk, карта, перевод, несие, аударым, депозит. Preserve the spoken language; do not translate.'},
             'noise_reduction': {'type': 'near_field'},
             'turn_detection': {'type': 'server_vad', 'threshold': 0.45,
                 'prefix_padding_ms': 300, 'silence_duration_ms': 5000 if pause == '5' else 550}}
    if language in {'ru', 'kk', 'en'}:
        audio['transcription']['language'] = language
    return {'type': 'transcription', 'audio': {'input': audio}}


async def proxy_voice(ws: WebSocket, state, settings, route_callback, authorized=lambda: True):
    """Bounded audio relay; a new utterance cancels a stale answer before playback."""
    tasks = []
    route_task = None
    try:
        if not settings.openai_key:
            await ws.close(code=1011, reason='OpenAI not configured')
            return
        await ws.accept()
        state.voice_active = True
        async with websockets.connect('wss://api.openai.com/v1/realtime?intent=transcription',
                additional_headers={'Authorization': 'Bearer ' + settings.openai_key},
                max_size=1024 * 1024, open_timeout=15, ping_interval=20) as upstream:
            await upstream.send(json.dumps({'type': 'session.update', 'session': session_config(
                settings, ws.query_params.get('language', 'auto'), ws.query_params.get('pause', 'auto'))}))
            start = time.monotonic()
            audio_bytes = 0
            turn_start = None
            last_auth = start
            generation = 0
            finals = asyncio.Queue(maxsize=4)
            pending = {}

            async def receive_browser():
                nonlocal audio_bytes, turn_start, last_auth
                async for message in ws.iter_bytes():
                    now = time.monotonic()
                    if now - last_auth > 5:
                        if not authorized():
                            raise ValueError('authentication_expired')
                        last_auth = now
                    if len(message) > 24000 or len(message) % 2:
                        raise ValueError('audio_chunk_limit')
                    if now - start > settings.ttl:
                        raise ValueError('voice_session_expired')
                    state.last_activity_at = time.time()
                    audio_bytes += len(message)
                    if audio_bytes > int((now - start + 2) * 48000 * 1.3):
                        raise ValueError('audio_rate_limit')
                    if turn_start and now - turn_start > settings.max_audio_seconds:
                        raise ValueError('audio_turn_limit')
                    await upstream.send(json.dumps({'type': 'input_audio_buffer.append',
                                                    'audio': base64.b64encode(message).decode()}))

            async def receive_provider():
                nonlocal turn_start, generation, route_task
                async for raw in upstream:
                    event = json.loads(raw)
                    kind, item = event.get('type'), event.get('item_id')
                    if kind == 'session.updated':
                        await ws.send_json({'type': 'ready'})
                    elif kind == 'input_audio_buffer.speech_started':
                        generation += 1
                        turn_start = time.monotonic()
                        pending.clear()
                        while not finals.empty():
                            finals.get_nowait()
                        if route_task and not route_task.done():
                            route_task.cancel()
                        pending[item] = {'generation': generation, 'partial': '', 'end': None}
                        await ws.send_json({'type': 'speech_started', 'turn': generation})
                    elif kind == 'input_audio_buffer.speech_stopped':
                        turn_start = None
                        if item in pending:
                            pending[item]['end'] = time.perf_counter()
                            await ws.send_json({'type': 'speech_stopped', 'turn': generation})
                    elif kind == 'conversation.item.input_audio_transcription.delta' and item in pending:
                        data = pending[item]
                        data['partial'] = (data['partial'] + event.get('delta', ''))[:4000]
                        await ws.send_json({'type': 'partial', 'text': data['partial'], 'turn': data['generation']})
                    elif kind == 'conversation.item.input_audio_transcription.completed' and item in pending:
                        data = pending.pop(item)
                        text = event.get('transcript', '').strip()[:4000]
                        if not text:
                            await ws.send_json({'type': 'error', 'message': 'Не расслышала фразу. Повторите, пожалуйста.'})
                            continue
                        await finals.put((text, data['end'] or time.perf_counter(), data['generation']))
                    elif kind == 'error':
                        raise ValueError('provider_error')
                    elif kind == 'conversation.item.input_audio_transcription.failed' and item in pending:
                        pending.pop(item, None)
                        await ws.send_json({'type': 'error', 'message': 'Не удалось распознать речь. Повторите, пожалуйста.'})

            async def recognition_watchdog():
                while True:
                    await asyncio.sleep(1)
                    for item, data in list(pending.items()):
                        if data['end'] and time.perf_counter() - data['end'] > 12:
                            pending.pop(item, None)
                            await ws.send_json({'type': 'error', 'message': 'Распознавание задерживается. Повторите фразу или напишите её.'})

            async def process_turns():
                nonlocal route_task
                while True:
                    text, end, version = await finals.get()
                    if version != generation:
                        continue
                    await ws.send_json({'type': 'final', 'text': text, 'turn': version})
                    try:
                        if not authorized():
                            raise ValueError('authentication_expired')
                        route_task = asyncio.create_task(route_callback(text, (time.perf_counter() - end) * 1000))
                        result = await route_task
                        if version == generation:
                            await ws.send_json({'type': 'result', 'data': result, 'turn': version})
                    except asyncio.CancelledError:
                        if asyncio.current_task().cancelling():
                            raise
                    except Exception:
                        if version == generation:
                            await ws.send_json({'type': 'error', 'message': 'Не удалось обработать фразу. Повторите или напишите её.'})

            tasks = [asyncio.create_task(c()) for c in
                     (receive_browser, receive_provider, process_turns, recognition_watchdog)]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
    except Exception:
        try:
            await ws.send_json({'type': 'error', 'message': 'Голосовое соединение прервано. Подключите микрофон снова или используйте текст.'})
        except Exception:
            pass
    finally:
        if route_task:
            route_task.cancel()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, *([route_task] if route_task else []), return_exceptions=True)
        state.voice_active = False
        try:
            await ws.close()
        except Exception:
            pass
