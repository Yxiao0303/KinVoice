"""Evidence links and deterministic support policy, not a clinical classifier."""
import re
from typing import Protocol
from .semantics import RuleSemanticJudge, current_intent
from .schemas import FieldAssessment
from .schemas import EvidenceLink, PolicyDecision, State, TurnRequest

STRATEGIES = ("listen", "clarify", "ground", "draft")
REFUSAL = re.compile(r"不要.{0,4}建议|别.{0,4}(建议|劝)|只.{0,5}(听我说|听听|倾听)|不想.{0,4}(沟通|和解|联系)|先别.{0,4}(建议|劝)")


def locate(req: TurnRequest, quote: str, purpose: str, current_only=False) -> EvidenceLink:
    # Prefer latest current evidence, then latest user turn. Assistant text is ineligible.
    sources = [("current", len(req.history), req.message)]
    if not current_only:
        sources.extend(("history", i, m.content) for i, m in reversed(list(enumerate(req.history))) if m.role == "user")
    for source, turn, content in sources:
        if quote and quote in content:
            start = content.index(quote)
            message_id = req.message_id if source == "current" else req.history[turn].message_id
            return EvidenceLink(message_id=message_id or f"{source}:{turn}", source=source, turn=turn, start=start, end=start+len(quote), quote=quote, purpose=purpose)
    raise ValueError("Evidence does not occur in eligible source")


def validate_state(req: TurnRequest, state: State, judge=None) -> list[EvidenceLink]:
    links = [locate(req, quote, "state") for quote in state.evidence]
    if (state.risk != "unknown" or state.family_unsafe or state.emotion != "unknown") and not links:
        raise ValueError("State requires evidence")
    if state.support_intent != "unknown" and not state.intent_evidence:
        raise ValueError("Intent requires current-turn evidence")
    links.extend(locate(req, quote, "intent", current_only=True) for quote in state.intent_evidence)
    judge = judge or RuleSemanticJudge()
    state.assessments = []  # Never trust provider-authored provenance.
    for field in ("risk", "family_unsafe", "emotion", "support_intent"):
        value = getattr(state, field)
        if value in ("unknown", False):
            continue
        candidates = [link for link in links if link.purpose == ("intent" if field == "support_intent" else "state")]
        verdicts = []
        for link in candidates:
            text = req.message if link.source == "current" else req.history[link.turn].content
            verdict = judge.assess(field, str(value).lower(), text)
            verdicts.append(verdict)
            state.assessments.append(FieldAssessment(field=field, value=str(value), verdict=verdict,
                message_id=link.message_id, current=link.source == "current",
                origin="explicit" if verdict == "supported" else "inferred"))
        supported = "supported" in verdicts and "contradicted" not in verdicts
        if not supported:
            state.needs_clarification = True
            # Safety is independent: uncertainty must never turn off the local guard.
            if field == "support_intent" or field == "emotion":
                setattr(state, field, "unknown")
            if field == "support_intent":
                state.intent_evidence = []
                links = [link for link in links if link.purpose != 'intent']
    return links


def decide(req: TurnRequest, state: State, links=None, *, intent_constraints=True, family_constraints=True) -> PolicyDecision:
    allowed, reasons = list(STRATEGIES), []
    evidence = list(links or [])
    selected = req.goal
    text_intent = current_intent(req.message) if intent_constraints else "unknown"
    refusal = REFUSAL.search(req.message) if text_intent == "listen" else None
    if state.risk == "urgent":
        return PolicyDecision(requested=req.goal, selected="safety", allowed=["safety"], reasons=["urgent_guard"], evidence=evidence)
    if state.family_unsafe and family_constraints:
        allowed.remove("draft")
        reasons.append("family_contact_restricted")
    effective_intent = text_intent if text_intent != "unknown" else state.support_intent if intent_constraints else "unknown"
    if refusal or effective_intent == "listen":
        allowed = ["listen"]
        reasons.append("current_refusal" if refusal else "current_listen_intent")
        if refusal:
            evidence.append(locate(req, refusal.group(), "intent", current_only=True))
    elif effective_intent != "unknown":
        # Explicit current words may refine the UI choice; never infer a durable profile.
        selected = effective_intent
        reasons.append("current_text_intent")
    if selected not in allowed:
        selected = "listen"
    if not reasons:
        reasons.append("user_selected_goal")
    return PolicyDecision(requested=req.goal, selected=selected, allowed=allowed, reasons=reasons, evidence=evidence)


class StrategySelector(Protocol):
    def select(self, req: TurnRequest, state: State, links: list[EvidenceLink]) -> PolicyDecision: ...


class RuleStrategySelector:
    def select(self, req, state, links):
        return decide(req, state, links)
