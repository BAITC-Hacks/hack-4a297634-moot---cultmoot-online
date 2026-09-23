import hashlib
import json
import logging
import re

def redact(text):
    text=re.sub(r'(?i)(bearer\s+)[^\s,;]+',r'\1[REDACTED]',str(text))
    text=re.sub(r'\b(?:sk-[A-Za-z0-9_-]{8,}|nvapi-[A-Za-z0-9_-]{8,})','[SECRET]',text)
    text=re.sub(r'(?<!\w)\+?\d[\d ()-]{8,}\d(?!\w)','[PII]',text)
    return text

def session_hash(sid): return hashlib.sha256(sid.encode()).hexdigest()[:12]

def log_event(**fields):
    allowed={'request_id','session_hash','scenario_id','provider','latency_ms','error_type','event'}
    logging.getLogger('voice_router').info(json.dumps({k:redact(v) if isinstance(v,str) else v for k,v in fields.items() if k in allowed},ensure_ascii=True))
