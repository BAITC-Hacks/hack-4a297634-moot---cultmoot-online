import hashlib
import json
import secrets
import time

YES={'да','да подтверждаю','подтверждаю','согласен','согласна','иә','растаймын','иә растаймын'}
NO={'нет','не подтверждаю','отмена','отменить','жоқ','бас тартамын'}

def confirmation_answer(text):
    # This is an explicit safety gate, never an intent classifier.
    text=text.strip().lower().strip('.!? ,')
    return 'yes' if text in YES else 'no' if text in NO else 'none'

def fingerprint(sid,scenario,action,slots):
    return hashlib.sha256(json.dumps([sid,scenario,action,slots],sort_keys=True).encode()).hexdigest()

def prepare_confirmation(state,scenario,action,slots):
    state.awaiting_confirmation={'scenario_id':scenario,'action':action,'slots':dict(slots),
        'fingerprint':fingerprint(state.session_id,scenario,action,slots),
        'nonce':secrets.token_urlsafe(24),'expires':time.time()+120}

def consume_confirmation(state,text):
    pending=state.awaiting_confirmation
    if not pending or confirmation_answer(text)!='yes': raise ValueError('explicit_confirmation_required')
    state.awaiting_confirmation=None
    if time.time()>pending['expires']: raise ValueError('confirmation_expired')
    expected=fingerprint(state.session_id,pending['scenario_id'],pending['action'],pending['slots'])
    if not secrets.compare_digest(expected,pending['fingerprint']): raise ValueError('confirmation_mismatch')
    # A single-use capability is created only after explicit affirmation, consumed by this call.
    token=secrets.token_urlsafe(32)
    return pending,hashlib.sha256(token.encode()).hexdigest()
