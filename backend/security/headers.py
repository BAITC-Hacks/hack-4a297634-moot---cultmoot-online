from starlette.responses import JSONResponse
from .rate_limit import RateLimiter
import asyncio
from urllib.parse import urlsplit

class SecurityMiddleware:
    def __init__(self,app,settings):
        self.app,self.settings=app,settings; self.rates=RateLimiter()
    async def __call__(self,scope,receive,send):
        if scope['type']!='http': return await self.app(scope,receive,send)
        headers=dict(scope['headers']); path=scope['path']; method=scope['method']
        origin=headers.get(b'origin',b'').decode(); host=urlsplit('//'+headers.get(b'host',b'').decode()).hostname
        async def reject(code,msg,extra=None):
            await JSONResponse({'detail':msg},status_code=code,headers=extra)(scope,receive,send)
        if host not in self.settings.allowed_hosts:
            return await reject(403,'Host not allowed')
        if self.settings.env=='production' and scope.get('scheme')!='https':return await reject(403,'HTTPS required')
        if headers.get(b'sec-fetch-site')==b'cross-site' and path.startswith('/api/'):
            return await reject(403,'Cross-site API request denied')
        if origin and origin not in self.settings.origins: return await reject(403,'Origin not allowed')
        if method in {'POST','PUT','DELETE','PATCH'} and not origin and host!='testserver':
            return await reject(403,'Origin required')
        ip=(scope.get('client') or ('unknown',))[0]
        category='token' if path.startswith('/api/realtime') else 'route' if path=='/api/route' else 'general'
        limit={'token':5,'route':30,'general':180}[category]
        retry=self.rates.check((ip,category),limit)
        if retry: return await reject(429,'Too many requests',{'Retry-After':str(retry)})
        if method in {'POST','PUT','PATCH'}:
            try: length=int(headers.get(b'content-length',b'0'))
            except ValueError: return await reject(400,'Invalid Content-Length')
            if length<0:return await reject(400,'Invalid Content-Length')
            if length>16384: return await reject(413,'Request exceeds 16 KB')
            content_type=headers.get(b'content-type',b'').decode().split(';')[0]
            if path.startswith('/api/') and content_type!='application/json': return await reject(415,'JSON required')
            body=bytearray()
            deadline=asyncio.get_running_loop().time()+5
            while True:
                try:
                    async with asyncio.timeout_at(deadline):message=await receive()
                except TimeoutError:return await reject(408,'Request body timeout')
                if message['type']=='http.disconnect': return
                body.extend(message.get('body',b''))
                if len(body)>16384: return await reject(413,'Request exceeds 16 KB')
                if not message.get('more_body'): break
            done=False
            async def replay():
                nonlocal done
                if not done:
                    done=True; return {'type':'http.request','body':bytes(body),'more_body':False}
                return await receive()
            inner_receive=replay
        else: inner_receive=receive
        async def secure_send(message):
            if message['type']=='http.response.start':
                h=list(message.get('headers',[]))
                csp="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self' https://api.openai.com; worker-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
                for k,v in {'Content-Security-Policy':csp,'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
                  'Permissions-Policy':'microphone=(self), camera=(), geolocation=()','X-Frame-Options':'DENY','Cache-Control':'no-store',
                  'Cross-Origin-Resource-Policy':'same-origin','Cross-Origin-Opener-Policy':'same-origin','X-DNS-Prefetch-Control':'off'}.items():
                    h.append((k.lower().encode(),v.encode()))
                if self.settings.env=='production':h.append((b'strict-transport-security',b'max-age=31536000; includeSubDomains'))
                message['headers']=h
            await send(message)
        await self.app(scope,inner_receive,secure_send)
