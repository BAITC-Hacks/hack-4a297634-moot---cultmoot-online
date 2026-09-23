import json
from pydantic import ValidationError
from .base import RouterProvider, InvalidOutput
from ..router.schema import Decision, CompactDecision, COMPACT_SCHEMA
from ..router.policy import confirmation_answer

class OpenAIRouterProvider(RouterProvider):
    name='openai'
    async def route(self,prefix,data):
        result=await self.request('/responses',{
            'model':self.model,'store':False,'instructions':prefix+'\nUse only fields in the compact schema. The server derives confirmation, missing slots, topic flags and response mode. Keep reason_short under 12 words.',
            'input':[{'role':'user','content':json.dumps(data,ensure_ascii=False,separators=(',',':'))}],
            'text':{'format':{'type':'json_schema','name':'router_decision_compact','strict':True,'schema':COMPACT_SCHEMA}},
            'max_output_tokens':650,
        })
        if result.get('status')!='completed': raise InvalidOutput('incomplete_or_refused')
        text=''.join(c.get('text','') for o in result.get('output',[]) for c in o.get('content',[]) if c.get('type')=='output_text')
        try:
            compact=CompactDecision.model_validate_json(text)
            state=data.get('state',{})
            d=Decision(**compact.model_dump(),missing_slots=[],requires_confirmation=False,
              topic_changed=bool(state.get('active_scenario') and state['active_scenario']!=compact.scenario_id),
              previous_topic_pending=bool(state.get('pending_topics')),
              confirmation=confirmation_answer(data.get('transcript','')) if state.get('awaiting_confirmation') else 'none',
              response_mode='handoff' if compact.decision=='handoff' else 'knowledge' if compact.action=='provide_information' else 'template' if compact.action in {'ask_slot','ask_clarification'} else 'backend')
        except ValidationError: raise InvalidOutput('schema_invalid') from None
        return d,result.get('usage',{})
