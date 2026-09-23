import asyncio
import copy
import json
import logging
import math
import secrets
import time
import re
from collections import deque
from contextlib import asynccontextmanager
from uuid import UUID,uuid4
import httpx
from fastapi import FastAPI,Request,Response,HTTPException,WebSocket
from fastapi.responses import FileResponse,StreamingResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field,ConfigDict
from .config import ROOT,settings
from .providers.openai_provider import OpenAIRouterProvider
from .router.scenario_adapter import Catalog
from .router.state import SessionStore
from .router.engine import Engine,normalize
from .services.mock_backend import MockBackend
from .services.knowledge import Knowledge
from .security.headers import SecurityMiddleware
from .security.rate_limit import RateLimiter
from .security.redaction import log_event,session_hash,redact
from .voice.realtime import proxy_voice,session_config
from . import accounts,tutorials

catalog=Catalog(ROOT/settings.catalog_path)
store=SessionStore(settings.ttl); rates=RateLimiter(); samples=deque(maxlen=500)
http=None;engine=None;providers={}

@asynccontextmanager
async def lifespan(app):
    global http,engine,providers
    accounts.initialize()
    http=httpx.AsyncClient(timeout=settings.timeout,limits=httpx.Limits(max_connections=30,max_keepalive_connections=15))
    providers={'openai':OpenAIRouterProvider(http,settings.openai_key,settings.openai_model,'https://api.openai.com/v1',settings.timeout)}
    engine=Engine(catalog,providers,MockBackend(ROOT/'backend/data/mock_backend.json'),
                  Knowledge(ROOT/'backend/data/knowledge_base.demo.json',settings.mode=='demo'),settings)
    async def cleanup():
        while True: await asyncio.sleep(30);store.cleanup()
    task=asyncio.create_task(cleanup())
    logging.getLogger('voice_router').info('Voice Router startup mode=%s scenarios=%d providers=%s',settings.mode,len(catalog.by_id),','.join(k for k,v in providers.items() if v.configured))
    yield
    task.cancel();await asyncio.gather(task,return_exceptions=True);await http.aclose()

app=FastAPI(title='Voice Router — HackAlem',lifespan=lifespan,docs_url=None,redoc_url=None)
app.add_middleware(SecurityMiddleware,settings=settings)

def session(request,csrf=True):
    u=current_user(request)
    s=store.get(request.cookies.get('vr_session'))
    if not s or s.user_id!=u['id']: raise HTTPException(401,'Сессия истекла. Обновите страницу.')
    if csrf and not secrets.compare_digest(request.headers.get('x-csrf-token',''),s.csrf): raise HTTPException(403,'Invalid CSRF token')
    return s

def current_user(request):
    u=accounts.user(request.cookies.get('vr_auth'))
    if not u:raise HTTPException(401,'Войдите в аккаунт.')
    return u

class Credentials(BaseModel):
    email:str=Field(min_length=3,max_length=254)
    password:str=Field(min_length=10,max_length=128)

@app.post('/api/auth/{action}')
async def authenticate(action:str,body:Credentials,request:Request,response:Response):
    if action not in {'login','register'}:raise HTTPException(404)
    email=body.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(422,'Проверьте адрес email.')
    retry=rates.check(('auth',request.client.host),8)
    if retry:raise HTTPException(429,'Подождите минуту перед следующей попыткой.')
    u=await asyncio.to_thread(accounts.register if action=='register' else accounts.login,email,body.password)
    if not u:raise HTTPException(400,'Не удалось войти или создать аккаунт. Проверьте данные.')
    old=store.get(request.cookies.get('vr_session'))
    if old:store.delete(old.session_id)
    accounts.revoke(request.cookies.get('vr_auth'))
    response.delete_cookie('vr_session')
    response.set_cookie('vr_auth',accounts.issue(u['id']),httponly=True,secure=settings.env=='production',samesite='strict',max_age=86400,path='/')
    return {'user':u}

@app.get('/api/me')
async def me(request:Request):return {'user':current_user(request)}

@app.post('/api/logout')
async def logout(request:Request,response:Response):
    s=session(request);store.delete(s.session_id);accounts.revoke(request.cookies.get('vr_auth'))
    response.delete_cookie('vr_auth');response.delete_cookie('vr_session')
    return {'ok':True}

@app.get('/api/history')
async def saved_history(request:Request):return {'messages':accounts.history(current_user(request)['id'])}

@app.delete('/api/history')
async def erase_history(request:Request):
    s=session(request);accounts.clear(s.user_id)
    for state in store.sessions.values():
        if state.user_id==s.user_id:state.conversation_history=[]
    return {'ok':True}

def limited(s,category,limit):
    retry=rates.check((s.session_id,category),limit)
    if retry: raise HTTPException(429,'Слишком много запросов.',headers={'Retry-After':str(retry)})

def percentile(vals,p):
    if not vals:return None
    vals=sorted(vals);return round(vals[min(len(vals)-1,math.ceil(len(vals)*p)-1)],1)

@app.get('/health/live')
async def live():return {'status':'live'}

@app.get('/health/ready')
async def ready():
    configured=bool(engine and providers.get(engine.primary()) and providers[engine.primary()].configured)
    return JSONResponse({'ready':configured,'catalog_loaded':bool(catalog.by_id),'scenario_count':len(catalog.by_id),
                        'mode':settings.mode,'provider_configuration_valid':configured},status_code=200 if configured else 503)

@app.post('/api/session')
async def create(request:Request,response:Response):
    u=current_user(request)
    old=store.get(request.cookies.get('vr_session'))
    if old and old.user_id==u['id']:return {'csrf':old.csrf,'state':old.context(),'history':old.conversation_history,'mode':settings.mode}
    try:s=store.create()
    except ValueError:raise HTTPException(429,'Session capacity reached',headers={'Retry-After':'30'})
    s.user_id=u['id']
    response.set_cookie('vr_session',s.session_id,httponly=True,secure=settings.env=='production',samesite='strict',max_age=settings.ttl,path='/')
    return {'csrf':s.csrf,'state':s.context(),'history':[],'mode':settings.mode}

@app.delete('/api/session')
async def delete(request:Request,response:Response):
    s=session(request);store.delete(s.session_id);response.delete_cookie('vr_session');return {'ended':True}

@app.get('/api/diagnostics')
async def diagnostics(request:Request):
    session(request,False)
    return {'providers':{k:v.health() for k,v in providers.items()},'scenario_count':len(catalog.by_id),'mode':settings.mode,
      'active_sessions':len(store.sessions),'active_voice_sessions':sum(s.voice_active for s in store.sessions.values()),
      'router_p50_ms':percentile([s['router'] for s in samples],.5),'router_p95_ms':percentile([s['router'] for s in samples],.95),
      'error_rate':sum(s['error'] for s in samples)/len(samples) if samples else None,
      'observed_turns':len(samples),'audio_retention':False}

class Turn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    text:str=Field(min_length=1,max_length=4000)
    request_id:UUID

async def run_turn(state,text,request_id,stt_ms=0):
    text=normalize(text)
    if not text or len(text)>4000:raise HTTPException(422,'Пустая или слишком длинная реплика.')
    limited(state,'route',30)
    async with state.lock:
        if request_id in state.results:return state.results[request_id]
        started=time.perf_counter();t=started
        quick=tutorials.handle(text,state)
        if quick is not None:return simple_result(state,text,quick,request_id,started)
        d,audit=await engine.decide(text,state)
        router_ms=(time.perf_counter()-t)*1000;t=time.perf_counter()
        # engine.decide includes strict validation; capture final catalog validation independently.
        from .router.validator import validate
        validate(d,catalog,state)
        validation_ms=(time.perf_counter()-t)*1000;t=time.perf_counter()
        d,response,backend_result=engine.respond(text,d,state)
        backend_ms=(time.perf_counter()-t)*1000
        state.add_turn(text,response)
        accounts.save(state.user_id,state.session_id,redact(text),redact(response))
        scenario=catalog.by_id.get(d.scenario_id)
        latency={'audio_capture_ms':None,'stt_ms':round(stt_ms,2),'router_ms':round(router_ms,2),
                 'validator_ms':round(validation_ms,2),'backend_ms':round(backend_ms,2),'tts_ms':None,
                 'first_audio_ms':None,'total_ms':round((time.perf_counter()-started)*1000+stt_ms,2)}
        trace={'request_id':request_id,'transcript':redact(text),'language':d.language,'decision':d.decision,
          'scenario_id':d.scenario_id,'scenario_name':scenario.name_kk if scenario and d.language=='kk' else scenario.name_ru if scenario else None,
          'confidence':d.confidence,'reason_short':d.reason_short,'alternatives':[a.model_dump() | {'name_ru':catalog.by_id[a.scenario_id].name_ru,'name_kk':catalog.by_id[a.scenario_id].name_kk} for a in d.alternatives],
          'topic_changed':d.topic_changed,'action':d.action,'provider':audit['provider'],'latency':latency,
          'validation_errors':audit['errors'],'attempts':audit['attempts'],'requires_confirmation':d.requires_confirmation}
        result={'response':response,'trace':trace,'state':state.context(),'backend':backend_result,
                'audio_url':'/api/audio/'+request_id if settings.openai_key else None}
        state.audio_responses[request_id]={'text':response,'created':time.time(),'started':started-stt_ms/1000,'plays':0,'trace':trace}
        state.results[request_id]=result
        for cache in [state.results,state.audio_responses]:
            while len(cache)>10:del cache[next(iter(cache))]
        samples.append({'router':router_ms,'error':bool(audit['errors'])})
        log_event(event='turn',request_id=request_id,session_hash=session_hash(state.session_id),scenario_id=d.scenario_id,
                  provider=audit['provider'],latency_ms=round(router_ms,2),error_type=','.join(audit['errors']) or None)
        return result

def simple_result(state,text,response,request_id,started=None):
    started=started or time.perf_counter()
    trace={'request_id':request_id,'transcript':redact(text),'language':state.language,'decision':'guide',
      'scenario_id':None,'scenario_name':'Пошаговая помощь','confidence':1,'reason_short':'Проверенная интерактивная подсказка',
      'alternatives':[],'topic_changed':False,'action':'guide','provider':'local','latency':{'router_ms':0,'total_ms':0},
      'validation_errors':[],'attempts':0,'requires_confirmation':False}
    result={'response':response,'trace':trace,'state':state.context(),'backend':None,'audio_url':'/api/audio/'+request_id,
      'tutorial':tutorials.view(state),'tutorial_offer':bool(state.tutorial_pending)}
    state.add_turn(text,response);accounts.save(state.user_id,state.session_id,redact(text),redact(response))
    state.audio_responses[request_id]={'text':response,'created':time.time(),'started':started,'plays':0,'trace':trace}
    state.results[request_id]=result
    for cache in (state.results,state.audio_responses):
        while len(cache)>10:del cache[next(iter(cache))]
    return result

class GuideAction(BaseModel):
    action:str
    index:int=Field(default=0,ge=0,le=20)

@app.post('/api/tutorial')
async def guide_action(body:GuideAction,request:Request):
    s=session(request);limited(s,'guide',40)
    async with s.lock:
        if body.action=='accept':
            if not s.tutorial_pending:raise HTTPException(409,'Сначала попросите показать подсказку.')
            answer=tutorials.handle('иә' if s.language=='kk' else 'да',s)
        elif body.action=='close':
            s.tutorial_active=None;s.tutorial_pending=None
            return {'closed':True}
        elif body.action=='step' and s.tutorial_active:
            s.tutorial_step=min(body.index,len(tutorials.GUIDES[s.tutorial_active]['steps'])-1)
            answer=tutorials.view(s)['steps'][s.tutorial_step]['text']
        else:raise HTTPException(400,'Неизвестное действие')
        return simple_result(s,'[Подсказка]',answer,str(uuid4()))

@app.post('/api/route')
async def route_turn(body:Turn,request:Request):
    return await run_turn(session(request),body.text,str(body.request_id))

@app.get('/api/audio/{request_id}')
async def audio(request_id:UUID,request:Request):
    s=session(request,False);limited(s,'tts',40)
    entry=s.audio_responses.get(str(request_id))
    if not entry or time.time()-entry['created']>180 or entry['plays']>=2:raise HTTPException(404,'Audio expired')
    entry['plays']+=1;t=time.perf_counter()
    upstream=await http.send(http.build_request('POST','https://api.openai.com/v1/audio/speech',
      headers={'Authorization':'Bearer '+settings.openai_key},json={'model':settings.tts_model,'voice':settings.voice,
       'input':entry['text'],'response_format':'mp3','instructions':'You are a friendly female assistant speaking naturally to one person. Warm, relaxed, reassuring, expressive conversational intonation, gentle smile, short natural pauses. Never sound like a robot, announcer or scripted call center. Speak clearly at a comfortable, slightly brisk pace. Preserve the language of the text, Russian or Kazakh, with natural pronunciation. Do not add words.'}),stream=True)
    if upstream.status_code!=200:
        await upstream.aclose();raise HTTPException(502,'Озвучивание недоступно; текстовый ответ сохранён.')
    async def generate():
        first=True
        try:
            async for chunk in upstream.aiter_bytes():
                if first:
                    entry['trace']['latency']['first_audio_ms']=round((time.perf_counter()-entry['started'])*1000,2);first=False
                yield chunk
        finally:
            await upstream.aclose()
            entry['trace']['latency']['tts_ms']=round((time.perf_counter()-t)*1000,2)
            entry['trace']['latency']['total_ms']=round((time.perf_counter()-entry['started'])*1000,2)
    return StreamingResponse(generate(),media_type='audio/mpeg')

@app.get('/api/trace/{request_id}')
async def trace(request_id:UUID,request:Request):
    s=session(request,False);r=s.results.get(str(request_id))
    if not r:raise HTTPException(404,'Trace not found')
    return r['trace']

@app.post('/api/realtime/token')
async def realtime_token(request:Request):
    s=session(request);limited(s,'realtime_token',3)
    if not settings.openai_key:raise HTTPException(503,'OpenAI not configured')
    if sum(x.voice_active for x in store.sessions.values())>=settings.max_voice and not s.voice_active:
        raise HTTPException(429,'Voice capacity reached',headers={'Retry-After':'30'})
    try:
        r=await http.post('https://api.openai.com/v1/realtime/client_secrets',
          headers={'Authorization':'Bearer '+settings.openai_key,'OpenAI-Safety-Identifier':session_hash(s.session_id)},
          json={'expires_after':{'anchor':'created_at','seconds':60},'session':session_config(settings)})
        if r.status_code!=200:raise HTTPException(502,'Realtime provider rejected session configuration')
        data=r.json()
        return {'value':data['value'],'expires_at':data['expires_at']}
    except httpx.HTTPError:raise HTTPException(502,'Realtime provider unavailable')

@app.websocket('/api/voice')
async def voice(ws:WebSocket):
    if ws.headers.get('origin') not in settings.origins:await ws.close(code=1008);return
    s=store.get(ws.cookies.get('vr_session'))
    u=accounts.user(ws.cookies.get('vr_auth'))
    if not s or not u or s.user_id!=u['id'] or s.voice_active:await ws.close(code=1008);return
    if sum(x.voice_active for x in store.sessions.values())>=settings.max_voice:await ws.close(code=1013);return
    retry=rates.check((s.session_id,'voice_connect'),5)
    if retry:await ws.close(code=1013);return
    await proxy_voice(ws,s,settings,lambda text,stt:run_turn(s,text,str(uuid4()),stt),lambda:bool(accounts.user(ws.cookies.get('vr_auth')) and store.get(s.session_id)))

dist=ROOT/'frontend/dist'
if dist.exists():
    app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')

@app.get('/')
@app.get('/login')
@app.get('/register')
@app.get('/assistant')
async def index():
    if not (dist/'index.html').exists():raise HTTPException(503,'Build frontend with npm run build first')
    return FileResponse(dist/'index.html')

@app.get('/pcm-worklet.js')
async def worklet():return FileResponse(ROOT/'frontend/public/pcm-worklet.js',media_type='application/javascript')
