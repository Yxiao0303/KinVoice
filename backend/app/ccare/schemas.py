from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, protected_namespaces=())


class Credentials(StrictModel):
    model_config = ConfigDict(str_strip_whitespace=False)
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    password: str = Field(min_length=10, max_length=100)


class HistoryMessage(StrictModel):
    message_id: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9:_-]+$")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ReviewEntry(StrictModel):
    field: Literal["emotion", "support_intent", "risk", "family_unsafe", "student_pressure", "student_subject", "student_time", "student_impact", "student_event"]
    value: str = Field(max_length=16)
    action: Literal["confirm", "correct", "revoke"]
    source_message_id: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9:_-]+$")
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_text: str = Field(min_length=1, max_length=2000)
    revision: int = Field(ge=0, le=1000000, strict=True)


class TurnRequest(StrictModel):
    message_id: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9:_-]+$")
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)
    goal: Literal["listen", "clarify", "ground", "draft"] = "listen"
    eligible: bool = False
    external_consent: bool = False
    reviews: list[ReviewEntry] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def eligible_reviews(self):
        ids = [m.message_id or f"history:{i}" for i, m in enumerate(self.history)] + [self.message_id or f"current:{len(self.history)}"]
        if len(ids) != len(set(ids)):
            raise ValueError("Message IDs must be unique within context")
        from .reviews import validate_reviews
        validate_reviews(self)
        return self

    @field_validator("history")
    @classmethod
    def bounded_history(cls, value):
        if sum(len(m.content) for m in value) > 16000:
            raise ValueError("History exceeds context budget")
        return value


class FieldAssessment(StrictModel):
    field: str
    value: str
    origin: Literal["explicit", "confirmed", "inferred", "unknown"] = "inferred"
    verdict: Literal["supported", "contradicted", "insufficient"]
    message_id: str
    role: Literal["user"] = "user"
    current: bool
    supersedes: str | None = None


class State(StrictModel):
    assessments: list[FieldAssessment] = Field(default_factory=list, max_length=30)
    needs_clarification: bool = False
    risk: Literal["unknown", "ordinary", "urgent"] = "unknown"
    family_unsafe: bool = Field(default=False, strict=True)
    emotion: Literal["unknown", "sad", "angry", "afraid", "mixed"] = "unknown"
    evidence: list[str] = Field(default_factory=list, max_length=5)
    # Only current-turn evidence may establish this temporary preference.
    support_intent: Literal["unknown", "listen", "clarify", "ground", "draft"] = "unknown"
    intent_evidence: list[str] = Field(default_factory=list, max_length=3)


class EvidenceLink(StrictModel):
    message_id: str = ""
    role: Literal["user"] = "user"
    source: Literal["current", "history"]
    turn: int
    start: int
    end: int
    quote: str
    purpose: Literal["state", "intent", "local_guard"]


class PolicyDecision(StrictModel):
    requested: str
    selected: str
    allowed: list[str]
    reasons: list[str]
    evidence: list[EvidenceLink] = Field(default_factory=list)


class StageRecord(StrictModel):
    stage: str
    status: Literal["completed", "failed", "cancelled"]
    elapsed_ms: int
    requested_model: str | None = None
    model: str | None = None
    usage: dict | None = None
    error_code: str | None = None


class Check(StrictModel):
    safe: bool = Field(strict=True)
    violations: list[str] = Field(default_factory=list, max_length=10)


class TurnResponse(StrictModel):
    review_targets: list[dict] = Field(default_factory=list)
    review_outcomes: list[dict] = Field(default_factory=list)
    reply: str
    mode: Literal["demo", "remote", "safety_template", "safe_fallback"]
    strategy: str
    state: State
    checks: list[str]
    model_calls: int
    usage: list[dict | None]
    policy_version: str = "ccare-prototype-0.4"
    decision: PolicyDecision | None = None
    stages: list[StageRecord] = Field(default_factory=list)
    failure_code: str | None = None
    elapsed_ms: int = 0
