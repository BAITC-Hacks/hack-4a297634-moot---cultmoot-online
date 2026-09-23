import unicodedata
import asyncio
import re
from ..config import ROOT
from ..providers.base import ProviderFailure, InvalidOutput
from .validator import validate, Rejected, safe_decision
from .policy import confirmation_answer, prepare_confirmation, consume_confirmation

def normalize(text): return ' '.join(unicodedata.normalize('NFKC',text).split())

class Engine:
    def __init__(self,catalog,providers,backend,knowledge,settings):
        self.catalog,self.providers,self.backend,self.knowledge,self.settings=catalog,providers,backend,knowledge,settings
        self.prefix=(ROOT/'backend/prompts/router_system.txt').read_text()+ '\nSCENARIO_CATALOG:\n'+catalog.prefix
        self.exact_examples={}
        for scenario in catalog.scenarios:
            for lang,examples in [('ru',scenario.examples_ru),('kk',scenario.examples_kk),('mixed',scenario.examples_mixed)]:
                for example in examples:
                    key=normalize(example).casefold().strip(' .!?')
                    prior=self.exact_examples.get(key)
                    self.exact_examples[key]=(scenario.id,lang) if key not in self.exact_examples or prior==(scenario.id,lang) else None

    def primary(self):
        return 'openai'

    async def decide(self,text,state):
        exact=self.exact_examples.get(normalize(text).casefold().strip(' .!?'))
        if exact and not state.active_scenario and not state.awaiting_confirmation and not state.pending_topics and not re.search(r'\d',text):
            sid,lang=exact;s=self.catalog.by_id[sid]
            action='handoff' if s.handoff else 'ask_slot' if s.required_slots else 'provide_information' if 'provide_information' in s.allowed_actions else None
            if action:
                d=safe_decision(self.catalog,lang,handoff=s.handoff).model_copy(update={
                    'decision':'handoff' if s.handoff else 'route','scenario_id':sid,'confidence':1.0,
                    'reason_short':'Точное однозначное совпадение с проверенным примером.',
                    'action':action,'context_sufficient':True,'response_mode':'handoff' if s.handoff else 'knowledge' if action=='provide_information' else 'template'})
                validate(d,self.catalog,state,text)
                return d,{'provider':'local_exact','attempts':0,'errors':[],'usage':{},'fallback':False}
        data={'state':state.context(),'recent_turns':state.conversation_history[-10:],'transcript':text}
        name=self.primary()
        audit={'provider':name,'attempts':0,'errors':[],'usage':{},'fallback':False}
        # One bounded request. A failed validation asks a safe clarification without a second slow call.
        for attempt in range(1):
            audit['attempts']+=1
            try:
                async with asyncio.timeout(self.settings.router_deadline):
                    d,usage=await self.providers[name].route(self.prefix,data)
                validate(d,self.catalog,state,text)
                audit.update(provider=name,usage=usage)
                if d.decision not in {'clarify','handoff'} and (d.confidence<.65 or not d.context_sufficient or
                    any(d.confidence-a.confidence<.1 for a in d.alternatives)):
                    d=safe_decision(self.catalog,d.language,reason='Недостаточная уверенность или близкие сценарии.',
                        question=d.clarifying_question,pending=d.pending_scenario_ids)
                return d,audit
            except (InvalidOutput,Rejected) as e:
                audit['errors'].append(str(e))
                data['validation_error']=str(e)
                data['repair_instruction']='Return a corrected object satisfying the schema and catalog.'
            except TimeoutError:
                audit['errors'].append('router_deadline')
                break
            except ProviderFailure as e:
                audit['errors'].append(e.kind)
                break
        return safe_decision(self.catalog,state.language,handoff=state.clarification_count>=2,
            reason='Router не смог вернуть проверяемое решение.'),audit

    def respond(self,text,d,state):
        lang='kk' if d.language=='kk' else 'ru'; state.language=d.language
        for pending in d.pending_scenario_ids:
            if pending not in state.pending_topics and pending!=d.scenario_id: state.pending_topics.append(pending)
        if d.decision=='clarify':
            state.awaiting_confirmation=None
            state.clarification_count+=1
            if state.clarification_count>2:
                d=safe_decision(self.catalog,d.language,handoff=True,reason='Два уточнения не разрешили неоднозначность.')
            else:
                response=d.clarifying_question or ('Сұрағыңызды нақтылай аласыз ба?' if lang=='kk' else 'Уточните, пожалуйста, что именно вы хотите сделать?')
                return d,response,None
        if d.decision=='handoff':
            state.awaiting_confirmation=None; state.awaiting_slot=None
            return d,('Операторға беру сұранысы тіркелді. Бұл demo, нақты байланыс жоқ.' if lang=='kk'
                else 'Запрос на оператора зафиксирован. Это demo: реальное соединение с банком не выполняется.'),{'mock':True,'handoff_requested':True}
        sid=d.scenario_id; scenario=self.catalog.by_id[sid]; old=state.active_scenario
        if old and old!=sid:
            state.previous_scenarios.append(old)
            if old not in state.completed and old not in state.pending_topics: state.pending_topics.append(old)
            state.awaiting_confirmation=None
        state.active_scenario=sid
        state.pending_topics=[p for p in state.pending_topics if p!=sid][-8:]
        d.previous_topic_pending=bool(state.pending_topics)
        state.clarification_count=0
        slots=state.collected_slots.setdefault(sid,{})
        slots.update({s.name:s.value for s in d.extracted_slots})
        state.awaiting_slot=None
        if d.action=='provide_information':
            state.awaiting_confirmation=None; state.completed.add(sid)
            return d,self.knowledge.answer(sid,lang),{'source':'trusted_knowledge','mock':True}
        missing=[p for p in scenario.required_slots if not slots.get(p.name)]
        d.missing_slots=[p.name for p in missing]
        if missing:
            state.awaiting_confirmation=None; state.completed.discard(sid)
            state.awaiting_slot=missing[0].name; d.action='ask_slot'
            return d,('Айтыңыз: '+missing[0].label_kk if lang=='kk' else 'Назовите '+missing[0].label_ru)+'.',None
        if d.action=='ask_slot':
            # Never guess a bank action when the model failed to select one.
            return safe_decision(self.catalog,d.language,question='Какое действие выполнить?'),'Какое действие выполнить?',None
        if d.requires_confirmation:
            pending=state.awaiting_confirmation
            answer=confirmation_answer(text)
            same=pending and pending['scenario_id']==sid and pending['action']==d.action and pending['slots']==slots
            if same and answer=='no':
                state.awaiting_confirmation=None
                return d,('Әрекет тоқтатылды.' if lang=='kk' else 'Действие отменено.'),{'mock':True,'cancelled':True}
            if same and answer=='yes':
                try:
                    confirmed,capability=consume_confirmation(state,text)
                    result=self.backend.execute(state,scenario,confirmed['action'],confirmed['slots'],capability)
                except ValueError:
                    return safe_decision(self.catalog,d.language),('Растау мерзімі өтті. Қайта сұраңыз.' if lang=='kk' else 'Подтверждение истекло. Повторите запрос.'),None
            else:
                prepare_confirmation(state,sid,d.action,slots)
                label=scenario.name_kk if lang=='kk' else scenario.name_ru
                client=self.backend.clients.get(slots.get('client_id'),{})
                suffix=' •••• '+client['cards'][0]['last4'] if scenario.action_specs.get(d.action,{}).get('collection')=='cards' and client.get('cards') else ''
                return d,(f'«{label}{suffix}» сынақ әрекетін растайсыз ба? «Иә» немесе «жоқ» деңіз.' if lang=='kk'
                    else f'Подтверждаете demo-действие «{label}{suffix}» для {slots.get("client_id", "test")}? Скажите «да» или «нет».'),{'mock':True,'awaiting_confirmation':True}
        else:
            result=self.backend.execute(state,scenario,d.action,slots)
        if not result.get('ok'):
            return d,('Қазір ақпаратты тексеру мүмкін болмады.' if lang=='kk' else 'Сейчас не удалось проверить информацию. Проверьте синтетический идентификатор.'),result
        state.completed.add(sid)
        statuses=', '.join(r['id']+': '+r['status'] for r in result['records'][-3:])
        response=('Сынақ деректері: ' if lang=='kk' else 'Синтетические данные: ')+statuses+'. '+('Нақты банк операциясы орындалған жоқ.' if lang=='kk' else 'Реальная банковская операция не выполнялась.')
        if state.pending_topics:
            previous=self.catalog.by_id[state.pending_topics[-1]]
            response+=(f' «{previous.name_kk}» сұрағына оралайық па?' if lang=='kk' else f' Вернуться к вопросу «{previous.name_ru}»?')
        return d,response,result
