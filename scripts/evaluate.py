import argparse
import asyncio
import hashlib
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from backend.config import ROOT, settings
from backend.providers.openai_provider import OpenAIRouterProvider
from backend.router.scenario_adapter import Catalog
from backend.router.engine import Engine
from backend.router.state import Session
from backend.services.mock_backend import MockBackend
from backend.services.knowledge import Knowledge

def percentile(values,p):
    if not values: return None
    values=sorted(values); return round(values[min(len(values)-1,math.ceil(len(values)*p)-1)],2)

def summarize(rows):
    metrics={}
    for label,predicate in [('overall',lambda r:True)]+[(l,lambda r,l=l:r['language']==l) for l in ['ru','kk','mixed']]+[(c,lambda r,c=c:r['category']==c) for c in ['ambiguous','topic_switch','injection','multi_intent','boundary','base','unknown','asr']]:
        group=[r for r in rows if predicate(r)]
        metrics[label]={'n':len(group),'accuracy':sum(r['passed'] for r in group)/len(group) if group else None,
            'p50_ms':percentile([r['latency_ms'] for r in group],.5),'p95_ms':percentile([r['latency_ms'] for r in group],.95),
            'errors':sum(bool(r['errors']) for r in group)}
    return metrics

async def evaluate(limit=0,concurrency=2,output=None):
    provider='openai'
    catalog=Catalog(ROOT/settings.catalog_path)
    cases=json.loads((ROOT/'tests/data/demo_router_cases.json').read_text(encoding='utf-8'))
    if limit: cases=cases[:limit]
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=20,max_keepalive_connections=10)) as client:
        providers={'openai':OpenAIRouterProvider(client,settings.openai_key,settings.openai_model,'https://api.openai.com/v1',settings.timeout)}
        if not providers[provider].configured:
            report={'status':'NOT TESTED','reason':'provider_not_configured','provider':provider,'created_at':time.time()}
        else:
            engine=Engine(catalog,providers,MockBackend(ROOT/'backend/data/mock_backend.json'),Knowledge(ROOT/'backend/data/knowledge_base.demo.json'),settings)
            sem=asyncio.Semaphore(concurrency); rows=[]; throttle=asyncio.Lock(); next_call=0.0
            async def one(case):
                nonlocal next_call
                async with sem:
                    # Stay below 450k input tokens/min for a ~7k-token catalog.
                    async with throttle:
                        await asyncio.sleep(max(0,next_call-time.monotonic()))
                        next_call=time.monotonic()+1.2
                    s=Session()
                    for k,v in case.get('state',{}).items(): setattr(s,k,v)
                    s.conversation_history=case.get('history',[])
                    start=time.perf_counter()
                    d,audit=await engine.decide(case['utterance'],s)
                    if any(e in {'http_429','circuit_open'} for e in audit['errors']):
                        await asyncio.sleep(35)
                        d,audit=await engine.decide(case['utterance'],s)
                    passed=d.scenario_id==case['expected_scenario'] and not audit['errors']
                    if case['expected_decision'] in {'clarify','handoff'}: passed &= d.decision==case['expected_decision']
                    if case.get('expected_pending'): passed &= set(case['expected_pending'])<=set(d.pending_scenario_ids)
                    row={'id':case['id'],'language':case['language'],'category':case['category'],'utterance':case['utterance'],
                         'expected':case['expected_scenario'],'actual':d.scenario_id,'passed':bool(passed),
                         'decision':d.model_dump(),'errors':audit['errors'],'usage':audit['usage'],
                         'latency_ms':round((time.perf_counter()-start)*1000,2)}
                    rows.append(row)
                    if len(rows)%10==0: print(f'{provider}: {len(rows)}/{len(cases)} correct={sum(r["passed"] for r in rows)}',flush=True)
            await asyncio.gather(*(one(c) for c in cases))
            report={'status':'COMPLETED','provider':provider,'model':providers[provider].model,'catalog_hash':catalog.digest,
                    'dataset_hash':hashlib.sha256((ROOT/'tests/data/demo_router_cases.json').read_bytes()).hexdigest(),
                    'created_at':time.time(),'metrics':summarize(rows),'cost':None,'cost_note':'Token usage recorded; pricing not inferred.',
                    'confusion_matrix':dict(Counter(str(r['expected'])+' -> '+str(r['actual']) for r in rows if not r['passed'])),
                    'results':sorted(rows,key=lambda r:r['id'])}
    path=ROOT/(output or f'reports/evaluation-{provider}.json'); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=True,indent=2),flush=True)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--limit',type=int,default=0); p.add_argument('--concurrency',type=int,default=2); p.add_argument('--output')
    a=p.parse_args(); asyncio.run(evaluate(a.limit,a.concurrency,a.output))
