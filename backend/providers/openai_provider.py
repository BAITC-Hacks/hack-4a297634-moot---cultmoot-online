import json
from pydantic import ValidationError
from .base import RouterProvider, InvalidOutput
from ..router.schema import Decision, DECISION_SCHEMA

class OpenAIRouterProvider(RouterProvider):
    name='openai'
    async def route(self,prefix,data):
        result=await self.request('/responses',{
            'model':self.model,'store':False,'instructions':prefix,
            'input':[{'role':'user','content':json.dumps(data,ensure_ascii=False,separators=(',',':'))}],
            'text':{'format':{'type':'json_schema','name':'router_decision','strict':True,'schema':DECISION_SCHEMA}},
            'max_output_tokens':1000,
        })
        if result.get('status')!='completed': raise InvalidOutput('incomplete_or_refused')
        text=''.join(c.get('text','') for o in result.get('output',[]) for c in o.get('content',[]) if c.get('type')=='output_text')
        try: d=Decision.model_validate_json(text)
        except ValidationError: raise InvalidOutput('schema_invalid') from None
        return d,result.get('usage',{})
