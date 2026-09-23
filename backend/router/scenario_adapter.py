"""Normalize trusted external catalogs without rewriting IDs or adding scenarios."""
import hashlib
import json
from pathlib import Path
from .schema import NormalizedScenarioSchema

def as_list(value):
    return value if isinstance(value, list) else [value] if value else []

def adapt_catalog(raw):
    rows = raw.get('scenarios', raw.get('intents')) if isinstance(raw,dict) else raw
    if not isinstance(rows,list) or not rows:
        raise ValueError('Catalog must contain a nonempty scenario list')
    result = []
    for row in rows:
        sid = row.get('id', row.get('scenario_id'))
        name = row.get('name', sid)
        slots = row.get('required_slots', row.get('required_parameters', []))
        if isinstance(slots, dict):
            slots = [dict(name=k, **v) for k,v in slots.items()]
        normalized_slots = []
        for slot in slots:
            if isinstance(slot,str): slot = {'name':slot}
            normalized_slots.append({'name':slot['name'], 'label_ru':slot.get('label_ru',slot['name']),
                'label_kk':slot.get('label_kk',slot['name']), 'pattern':slot.get('pattern',r'.{1,100}'),
                'enum':slot.get('enum',[])})
        actions = row.get('allowed_actions', ['provide_information'])
        result.append(NormalizedScenarioSchema(
            id=sid, name_ru=row.get('name_ru',name), name_kk=row.get('name_kk',name),
            description=row.get('description',''), include_when=as_list(row.get('include_when',row.get('description',''))),
            exclude_when=as_list(row.get('exclude_when',row.get('boundaries',[]))),
            neighbor_scenarios=row.get('neighbor_scenarios',[]), required_slots=normalized_slots,
            allowed_actions=actions, requires_confirmation_actions=row.get('requires_confirmation_actions',[]),
            examples_ru=row.get('examples_ru',row.get('examples',[])), examples_kk=row.get('examples_kk',[]),
            examples_mixed=row.get('examples_mixed',[]), action_specs=row.get('action_specs',{}),
            handoff=row.get('handoff',False)))
    ids = {s.id for s in result}
    if len(ids) != len(result): raise ValueError('Duplicate scenario ID')
    for s in result:
        if not set(s.neighbor_scenarios) <= ids: raise ValueError('Unknown catalog neighbor')
        if not set(s.requires_confirmation_actions) <= set(s.allowed_actions): raise ValueError('Unknown confirmed action')
        if len({slot.name for slot in s.required_slots}) != len(s.required_slots): raise ValueError('Duplicate slot')
    return result

class Catalog:
    def __init__(self, path):
        self.path = Path(path)
        self.scenarios = adapt_catalog(json.loads(self.path.read_text(encoding='utf-8-sig')))
        self.by_id = {s.id:s for s in self.scenarios}
        cards = []
        for s in self.scenarios:
            cards.append({k:v for k,v in s.model_dump().items() if k not in {'action_specs','examples_ru','examples_kk','examples_mixed'}})
        self.prefix = json.dumps(cards, ensure_ascii=False, separators=(',',':'))
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.handoff_id = next((s.id for s in self.scenarios if s.handoff), None)
