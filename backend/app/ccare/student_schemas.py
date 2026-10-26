"""Student P1 types. Synthetic development only; no inferred age or diagnosis."""
from typing import Literal, Protocol
from pydantic import Field
from .schemas import StrictModel, TurnRequest, EvidenceLink, TurnResponse

Stage = Literal['middle', 'high', 'university']
class StudentProfile(StrictModel):
    stage: Stage = 'university'
    adult_confirmed: bool = Field(default=False, strict=True)
    synthetic_only: Literal[True] = True
    scenario: Literal['academic_family'] = 'academic_family'

class StudentRequest(TurnRequest):
    student: StudentProfile
    support: Literal['listen','organize','clarify','draft','small_step','options'] = 'listen'

class StudentClaim(StrictModel):
    field: Literal['student_pressure','student_subject','student_time','student_impact','student_event']
    value: str
    status: Literal['supported','unknown','confirmed','revoked'] = 'unknown'
    evidence: list[EvidenceLink] = Field(default_factory=list, max_length=5)
    revision: int = 0
    supersedes: str | None = None

class StudentEvent(StrictModel):
    event_id: str
    message_id: str
    source_digest: str
    provenance: Literal['self_report','reported','hypothetical','uncertain'] = 'uncertain'
    claims: list[StudentClaim]
    active: bool = True

class StudentJudgment(StrictModel):
    version: Literal['student-p1-v1'] = 'student-p1-v1'
    method: Literal['conservative_rules_unvalidated'] = 'conservative_rules_unvalidated'
    stage: Stage
    events: list[StudentEvent] = Field(default_factory=list,max_length=21)
    uncertainties: list[str]
    risk: Literal['unknown','ordinary','urgent'] = 'unknown'
    current_need: str = 'unknown'
    need_origin: Literal['explicit_text','user_choice','review','unknown'] = 'unknown'
    need_evidence: list[EvidenceLink] = Field(default_factory=list)
    action: str = 'listen'
    reasons: list[str] = Field(default_factory=list)
    basis_event_ids: list[str] = Field(default_factory=list)

class StudentResponse(TurnResponse):
    student_judgment: StudentJudgment

class StudentJudge(Protocol):
    def extract(self, req: StudentRequest) -> StudentJudgment: ...
