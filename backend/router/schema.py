from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Slot(Strict):
    name: str
    value: str

class Alternative(Strict):
    scenario_id: str
    confidence: float = Field(ge=0, le=1)

class Decision(Strict):
    decision: Literal['route','continue','clarify','handoff']
    scenario_id: str | None
    confidence: float = Field(ge=0, le=1)
    reason_short: str = Field(max_length=350)
    alternatives: list[Alternative] = Field(max_length=2)
    language: Literal['ru','kk','mixed','other']
    topic_changed: bool
    previous_topic_pending: bool
    pending_scenario_ids: list[str] = Field(max_length=4)
    extracted_slots: list[Slot] = Field(max_length=8)
    missing_slots: list[str] = Field(max_length=8)
    action: str
    requires_confirmation: bool
    confirmation: Literal['yes','no','none']
    clarifying_question: str | None
    response_mode: Literal['template','knowledge','backend','handoff']
    context_sufficient: bool

DECISION_SCHEMA = Decision.model_json_schema()

class SlotSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str
    label_ru: str
    label_kk: str
    pattern: str = r'.{1,100}'
    enum: list[str] = []

class NormalizedScenarioSchema(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=100)
    name_ru: str
    name_kk: str
    description: str
    include_when: list[str]
    exclude_when: list[str]
    neighbor_scenarios: list[str]
    required_slots: list[SlotSpec]
    allowed_actions: list[str]
    requires_confirmation_actions: list[str]
    examples_ru: list[str]
    examples_kk: list[str]
    examples_mixed: list[str]
    action_specs: dict = {}
    handoff: bool = False
