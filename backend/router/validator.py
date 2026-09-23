import re
from .schema import Decision

class Rejected(ValueError): pass

CONTROL_ACTIONS={'ask_slot','ask_clarification','handoff'}

def validate(d,catalog,state,transcript=None):
    ids=catalog.by_id
    if d.scenario_id is not None and d.scenario_id not in ids: raise Rejected('unknown_scenario')
    if any(a.scenario_id not in ids or a.scenario_id==d.scenario_id for a in d.alternatives): raise Rejected('invalid_alternative')
    if any(s not in ids for s in d.pending_scenario_ids): raise Rejected('unknown_pending')
    if len(set(p.name for p in d.extracted_slots))!=len(d.extracted_slots): raise Rejected('duplicate_slot')
    if d.decision=='clarify':
        if d.scenario_id is not None or d.action!='ask_clarification' or d.extracted_slots: raise Rejected('invalid_clarification')
        return d
    if d.decision=='handoff':
        if d.action!='handoff' or (d.scenario_id and not ids[d.scenario_id].handoff): raise Rejected('invalid_handoff')
        if d.extracted_slots: raise Rejected('handoff_slots')
        return d
    if not d.scenario_id: raise Rejected('missing_scenario')
    s=ids[d.scenario_id]
    if s.handoff: raise Rejected('handoff_requires_handoff_decision')
    if d.action not in s.allowed_actions+['ask_slot']: raise Rejected('unknown_action')
    if d.decision=='continue' and d.scenario_id!=state.active_scenario: raise Rejected('continue_wrong_topic')
    specs={p.name:p for p in s.required_slots}
    for p in d.extracted_slots:
        if p.name not in specs: raise Rejected('unknown_slot')
        spec=specs[p.name]
        if not re.fullmatch(spec.pattern,p.value) or (spec.enum and p.value not in spec.enum): raise Rejected('slot_format')
        if transcript is not None:
            sources=transcript+' '+ ' '.join(m['content'] for m in state.conversation_history[-10:] if m['role']=='user')
            prior=state.collected_slots.get(d.scenario_id,{})
            if p.value.casefold() not in sources.casefold() and prior.get(p.name)!=p.value:
                raise Rejected('slot_has_no_customer_source')
    if any(k not in specs for k in d.missing_slots): raise Rejected('unknown_missing_slot')
    # Deterministic policy, not model-provided requires_confirmation.
    spec=s.action_specs.get(d.action,{})
    d.requires_confirmation=(d.action in s.requires_confirmation_actions or spec.get('operation') in {'update','create','delete'})
    d.topic_changed=bool(state.active_scenario and state.active_scenario!=d.scenario_id)
    return d

def safe_decision(catalog,language='ru',handoff=False,reason='Недостаточно данных.',question=None,pending=None):
    return Decision(decision='handoff' if handoff else 'clarify',scenario_id=catalog.handoff_id if handoff else None,
        confidence=0.0,reason_short=reason,alternatives=[],language=language,topic_changed=False,
        previous_topic_pending=False,pending_scenario_ids=pending or [],extracted_slots=[],missing_slots=[],
        action='handoff' if handoff else 'ask_clarification',requires_confirmation=False,confirmation='none',
        clarifying_question=question,response_mode='handoff' if handoff else 'template',context_sufficient=False)
