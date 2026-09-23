import asyncio
import secrets
import time
from dataclasses import dataclass, field

@dataclass
class Session:
    session_id: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    language: str = 'ru'
    active_scenario: str | None = None
    previous_scenarios: list = field(default_factory=list)
    pending_topics: list = field(default_factory=list)
    collected_slots: dict = field(default_factory=dict)
    awaiting_slot: str | None = None
    awaiting_confirmation: dict | None = None
    clarification_count: int = 0
    last_activity_at: float = field(default_factory=time.time)
    conversation_history: list = field(default_factory=list)
    completed: set = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    results: dict = field(default_factory=dict)
    mock_records: dict = field(default_factory=dict)
    voice_active: bool = False
    audio_responses: dict = field(default_factory=dict)

    def context(self):
        return {k:getattr(self,k) for k in ('language','active_scenario','previous_scenarios','pending_topics',
            'collected_slots','awaiting_slot','clarification_count')} | {
            'awaiting_confirmation':{k:v for k,v in (self.awaiting_confirmation or {}).items() if k not in {'nonce','expires'}} or None}

    def add_turn(self,text,response):
        self.conversation_history.extend([{'role':'user','content':text},{'role':'assistant','content':response}])
        self.conversation_history=self.conversation_history[-40:]
        self.previous_scenarios=self.previous_scenarios[-20:]
        self.last_activity_at=time.time()

class SessionStore:
    def __init__(self,ttl=1800,max_sessions=200):
        self.ttl,self.max_sessions=ttl,max_sessions
        self.sessions={}

    def cleanup(self):
        now=time.time()
        for sid,s in list(self.sessions.items()):
            if now-s.last_activity_at>self.ttl and not s.lock.locked():
                del self.sessions[sid]

    def create(self):
        self.cleanup()
        if len(self.sessions)>=self.max_sessions: raise ValueError('session_capacity')
        s=Session(); self.sessions[s.session_id]=s; return s

    def get(self,sid):
        self.cleanup()
        s=self.sessions.get(sid or '')
        if s: s.last_activity_at=time.time()
        return s

    def delete(self,sid): self.sessions.pop(sid,None)
