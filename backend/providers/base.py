import asyncio
import time
from abc import ABC, abstractmethod
import httpx

class ProviderFailure(Exception):
    def __init__(self, kind, status=None):
        self.kind, self.status = kind, status
        super().__init__(kind)

class InvalidOutput(Exception):
    pass

class RouterProvider(ABC):
    name = ''
    def __init__(self, client, key, model, base_url, timeout=20):
        self.client, self.key, self.model, self.base_url = client, key, model, base_url.rstrip('/')
        self.timeout = timeout
        self.failures = 0
        self.open_until = 0.0
        self.last_error = None
        self.last_success = None

    @property
    def configured(self): return bool(self.key and self.model)

    def health(self):
        return {'configured':self.configured,'model':self.model or None,
                'circuit':'open' if time.monotonic()<self.open_until else 'closed',
                'last_error':self.last_error,'last_success_at':self.last_success}

    async def request(self, path, payload=None):
        if not self.key: raise ProviderFailure('not_configured')
        if time.monotonic()<self.open_until: raise ProviderFailure('circuit_open')
        try:
            response = await self.client.request('POST' if payload is not None else 'GET',
                self.base_url+path, json=payload, headers={'Authorization':'Bearer '+self.key}, timeout=self.timeout)
            if response.status_code>=400:
                raise ProviderFailure('http_'+str(response.status_code), response.status_code)
            data = response.json()
            self.failures = 0; self.last_error = None; self.last_success = time.time()
            return data
        except (httpx.HTTPError, ProviderFailure, ValueError) as error:
            self.failures += 1
            self.last_error = error.kind if isinstance(error,ProviderFailure) else type(error).__name__
            if self.failures>=3: self.open_until=time.monotonic()+30
            raise ProviderFailure(self.last_error, getattr(error,'status',None)) from None

    async def get_models(self):
        result=await self.request('/models')
        return sorted(m['id'] for m in result.get('data',[]) if isinstance(m,dict) and 'id' in m)

    async def benchmark(self, prefix, cases):
        out=[]
        for case in cases:
            t=time.perf_counter()
            try:
                d,usage=await self.route(prefix,case)
                out.append({'decision':d.model_dump(),'usage':usage,'latency_ms':(time.perf_counter()-t)*1000})
            except (ProviderFailure,InvalidOutput) as e:
                out.append({'error':str(e),'latency_ms':(time.perf_counter()-t)*1000})
        return out

    @abstractmethod
    async def route(self, prefix, data): ...
