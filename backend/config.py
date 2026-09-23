import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=False)

@dataclass
class Settings:
    env: str = field(default_factory=lambda: os.getenv('APP_ENV', '').strip() or 'development')
    mode: str = field(default_factory=lambda: os.getenv('APP_MODE', 'demo'))
    openai_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY', ''))
    openai_model: str = field(default_factory=lambda: os.getenv('OPENAI_ROUTER_MODEL', 'gpt-4.1'))
    realtime_model: str = field(default_factory=lambda: os.getenv('OPENAI_REALTIME_MODEL', 'gpt-4o-transcribe'))
    tts_model: str = field(default_factory=lambda: os.getenv('OPENAI_TTS_MODEL', 'gpt-4o-mini-tts'))
    voice: str = field(default_factory=lambda: os.getenv('OPENAI_TTS_VOICE', 'shimmer'))
    catalog_path: str = field(default_factory=lambda: os.getenv('SCENARIO_CATALOG_PATH', 'backend/data/scenarios.demo.halyk.json'))
    origins: list[str] = field(default_factory=lambda: os.getenv('ALLOWED_ORIGINS', 'http://localhost:8010,http://127.0.0.1:8010').split(','))
    ttl: int = field(default_factory=lambda: int(os.getenv('SESSION_TTL_MINUTES', '30')) * 60)
    timeout: float = field(default_factory=lambda: float(os.getenv('PROVIDER_TIMEOUT_SECONDS', '20')))
    router_deadline: float = field(default_factory=lambda: float(os.getenv('ROUTER_DEADLINE_SECONDS', '8')))
    allowed_hosts: list[str] = field(default_factory=lambda: os.getenv('ALLOWED_HOSTS','localhost,127.0.0.1,testserver').split(','))
    max_voice: int = field(default_factory=lambda: int(os.getenv('MAX_VOICE_SESSIONS', '4')))
    max_audio_seconds: int = field(default_factory=lambda: int(os.getenv('MAX_AUDIO_TURN_SECONDS', '45')))

    def __post_init__(self):
        if self.env not in {'development','production'}:raise ValueError('Invalid APP_ENV')
        if '*' in self.allowed_hosts:raise ValueError('Wildcard hosts are forbidden')
        if self.env=='production' and any(urlsplit(o).scheme!='https' for o in self.origins):
            raise ValueError('Production requires HTTPS origins')
        if not 1<=self.router_deadline<=30:raise ValueError('Router deadline must be between 1 and 30 seconds')
        if self.mode not in {'demo','official'}:
            raise ValueError('Invalid APP_MODE')
        if '*' in self.origins:
            raise ValueError('Wildcard origins are forbidden')
        if self.mode == 'official' and 'demo' in Path(self.catalog_path).name:
            raise ValueError('Official mode requires an official catalog, not demo data')
        if os.getenv('AUDIO_RETENTION','false').lower() != 'false':
            raise ValueError('Raw audio retention is not supported')

settings = Settings()
