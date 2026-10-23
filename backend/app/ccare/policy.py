"""Evidence links and deterministic support policy, not a clinical classifier."""
import re
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
            return EvidenceLink(source=source, turn=turn, start=start, end=start+len(quote), quote=quote, purpose=purpose)
    raise ValueError("Evidence does not occur in eligible source")


def validate_state(req: TurnRequest, state: State) -> list[EvidenceLink]:
    links = [locate(req, quote, "state") for quote in state.evidence]
    if (state.risk != "unknown" or state.family_unsafe or state.emotion != "unknown") and not links:
        raise ValueError("State requires evidence")
    if state.support_intent != "unknown" and not state.intent_evidence:
        raise ValueError("Intent requires current-turn evidence")
    links.extend(locate(req, quote, "intent", current_only=True) for quote in state.intent_evidence)
    return links


def decide(req: TurnRequest, state: State, links=None) -> PolicyDecision:
    allowed, reasons = list(STRATEGIES), []
    evidence = list(links or [])
    selected = req.goal
    refusal = REFUSAL.search(req.message)
    if state.risk == "urgent":
        return PolicyDecision(requested=req.goal, selected="safety", allowed=["safety"], reasons=["urgent_guard"], evidence=evidence)
    if state.family_unsafe:
        allowed.remove("draft")
        reasons.append("family_contact_restricted")
    if refusal or state.support_intent == "listen":
        allowed = ["listen"]
        reasons.append("current_refusal" if refusal else "current_listen_intent")
        if refusal:
            evidence.append(locate(req, refusal.group(), "intent", current_only=True))
    elif state.support_intent != "unknown":
        # Explicit current words may refine the UI choice; never infer a durable profile.
        selected = state.support_intent
        reasons.append("current_text_intent")
    if selected not in allowed:
        selected = "listen"
    if not reasons:
        reasons.append("user_selected_goal")
    return PolicyDecision(requested=req.goal, selected=selected, allowed=allowed, reasons=reasons, evidence=evidence)
