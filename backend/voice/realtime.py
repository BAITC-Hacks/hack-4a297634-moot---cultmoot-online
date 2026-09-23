import asyncio
import base64
import json
import time
import websockets
from fastapi import WebSocket

def session_config(settings):
    audio={'format':{'type':'audio/pcm','rate':24000},
           'transcription':{'model':settings.realtime_model,'prompt':'Банковский разговор: русский, қазақша, mixed RU/KZ. Halyk, карта, несие, аударым, депозит.'},
           'noise_reduction':{'type':'near_field'},
           'turn_detection':{'type':'server_vad','threshold':0.5,'prefix_padding_ms':300,'silence_duration_ms':650}}
    if settings.realtime_model=='gpt-live-transcribe':
        audio['turn_detection']=None
    return {'type':'transcription','audio':{'input':audio}}

async def proxy_voice(ws:WebSocket,state,settings,route_callback):
    """Bounded PCM stream. Standard API key never leaves the server."""
    if not settings.openai_key:
        await ws.close(code=1011,reason='OpenAI not configured');return
    await ws.accept()
    state.voice_active=True
    tasks=[]
    try:
        async with websockets.connect('wss://api.openai.com/v1/realtime?intent=transcription',
            additional_headers={'Authorization':'Bearer '+settings.openai_key},max_size=1024*1024,
            open_timeout=15,ping_interval=20) as upstream:
            await upstream.send(json.dumps({'type':'session.update','session':session_config(settings)}))
            start=time.monotonic(); audio_bytes=0; turn_start=None
            finals=asyncio.Queue(maxsize=4)
            item_order=[]; completed={}; stopped={}; partials={}
            async def receive_browser():
                nonlocal audio_bytes,turn_start
                async for message in ws.iter_bytes():
                    if len(message)>24000 or len(message)%2: raise ValueError('audio_chunk_limit')
                    if time.monotonic()-start>settings.ttl: raise ValueError('voice_session_expired')
                    state.last_activity_at=time.time()
                    audio_bytes+=len(message)
                    if audio_bytes>int((time.monotonic()-start+2)*48000*1.3): raise ValueError('audio_rate_limit')
                    if turn_start and time.monotonic()-turn_start>settings.max_audio_seconds: raise ValueError('audio_turn_limit')
                    await upstream.send(json.dumps({'type':'input_audio_buffer.append','audio':base64.b64encode(message).decode()}))
            async def receive_provider():
                nonlocal turn_start
                async for raw in upstream:
                    event=json.loads(raw); kind=event.get('type'); item=event.get('item_id')
                    if kind=='session.updated': await ws.send_json({'type':'ready'})
                    elif kind=='input_audio_buffer.speech_started':
                        turn_start=time.monotonic(); await ws.send_json({'type':'speech_started'})
                    elif kind=='input_audio_buffer.speech_stopped':
                        stopped[item]=time.perf_counter(); turn_start=None
                        await ws.send_json({'type':'speech_stopped'})
                    elif kind=='input_audio_buffer.committed': item_order.append(item)
                    elif kind=='conversation.item.input_audio_transcription.delta':
                        partials[item]=partials.get(item,'')+event.get('delta','')
                        await ws.send_json({'type':'partial','text':partials[item][:4000]})
                    elif kind=='conversation.item.input_audio_transcription.completed':
                        partials.pop(item,None);completed[item]=event.get('transcript','')
                        while item_order and item_order[0] in completed:
                            current=item_order.pop(0); text=completed.pop(current)
                            await finals.put((text,stopped.pop(current,time.perf_counter())))
                    elif kind=='error' or kind=='conversation.item.input_audio_transcription.failed':
                        await ws.send_json({'type':'error','message':'Не удалось точно распознать речь. Повторите, пожалуйста.'})
            async def process_turns():
                while True:
                    text,end=await finals.get()
                    if not text.strip(): continue
                    await ws.send_json({'type':'final','text':text})
                    result=await route_callback(text,(time.perf_counter()-end)*1000)
                    await ws.send_json({'type':'result','data':result})
            tasks=[asyncio.create_task(c()) for c in [receive_browser,receive_provider,process_turns]]
            done,pending=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            for task in done: task.result()
    except Exception:
        try: await ws.send_json({'type':'error','message':'Голосовое соединение прервано. Подключите микрофон снова или используйте текст.'})
        except Exception: pass
    finally:
        for task in tasks: task.cancel()
        if tasks: await asyncio.gather(*tasks,return_exceptions=True)
        state.voice_active=False
        try: await ws.close()
        except Exception: pass
