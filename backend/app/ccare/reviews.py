"""Request-scoped review reduction. No persistence or independent-safety override."""
import hashlib
from .schemas import FieldAssessment, ReviewEntry
from .semantics import current_intent

VALUES = {
    'emotion': ('unknown', 'sad', 'angry', 'afraid', 'mixed'),
    'support_intent': ('unknown', 'listen', 'clarify', 'ground', 'draft'),
    'risk': ('unknown', 'ordinary', 'urgent'),
    'family_unsafe': ('false', 'true'),
}


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sources(req):
    return [(m.message_id or f'history:{i}', m.content) for i, m in enumerate(req.history) if m.role == 'user'] + [(req.message_id or f'current:{len(req.history)}', req.message)]


def review_key(entry):
    return entry.field, entry.source_message_id or entry.source_digest


def reduce_reviews(entries):
    latest, seen = {}, {}
    for entry in entries:
        key = review_key(entry)
        previous = latest.get(key)
        version = (*key, entry.revision)
        if version in seen and seen[version] != entry:
            raise ValueError('Conflicting review revision')
        seen[version] = entry
        if previous is None or entry.revision > previous.revision:
            latest[key] = entry
    return list(latest.values())


def validate_reviews(req):
    eligible = {digest(text): text for _, text in sources(req)}
    by_id = dict(sources(req))
    for entry in reduce_reviews(req.reviews):
        if (entry.revision < 1 or eligible.get(entry.source_digest) != entry.source_text or entry.value not in VALUES[entry.field]
                or (entry.source_message_id is not None and by_id.get(entry.source_message_id) != entry.source_text)):
            raise ValueError('Review must reference eligible user source and a permitted value')


def apply_reviews(req, state, links, guard):
    """A newer user source wins. Tombstones stop a model resurrecting old claims.

    Only user-supplied review entries are authoritative; provider provenance is
    rebuilt by validate_state. Local guard is recomputed and restored below.
    """
    eligible = sources(req)
    rank = {digest(text): i for i, (_, text) in enumerate(eligible)}
    rank.update({mid: i for i, (mid, _) in enumerate(eligible)})
    source_by_id = dict(eligible)
    latest = sorted(reduce_reviews(req.reviews), key=lambda entry: (rank[entry.source_message_id or entry.source_digest], entry.revision))
    outcomes = []
    for entry in latest:
        newer = False
        for assessment in state.assessments:
            text = source_by_id.get(assessment.message_id)
            if assessment.field == entry.field and text is not None and rank[assessment.message_id] > rank[entry.source_message_id or entry.source_digest] and assessment.verdict == 'supported':
                newer = True
        if entry.field == 'support_intent' and (req.message_id or digest(req.message)) != (entry.source_message_id or entry.source_digest) and current_intent(req.message) != 'unknown':
            newer = True
        if newer:
            outcomes.append({'field': entry.field, 'revision': entry.revision, 'status': 'superseded'})
            continue
        value = ('false' if entry.field == 'family_unsafe' else 'unknown') if entry.action == 'revoke' else entry.value
        setattr(state, entry.field, value == 'true' if entry.field == 'family_unsafe' else value)
        state.assessments = [a for a in state.assessments if a.field != entry.field]
        message_id = entry.source_message_id or next(mid for mid, text in reversed(eligible) if digest(text) == entry.source_digest)
        state.assessments.append(FieldAssessment(field=entry.field, value=value,
            origin='unknown' if entry.action == 'revoke' else 'confirmed',
            verdict='insufficient' if entry.action == 'revoke' else 'supported',
            message_id=message_id, current=message_id == (req.message_id or f'current:{len(req.history)}'),
            supersedes=f'{entry.source_digest}:{entry.field}:{entry.revision-1}'))
        if entry.action == 'revoke':
            state.needs_clarification = True
            if entry.field == 'support_intent':
                state.intent_evidence = []
            if entry.field in ('emotion', 'risk', 'family_unsafe'):
                state.evidence = [quote for quote in state.evidence if quote not in entry.source_text]
            # Do not offer the withdrawn quote as active state/intent evidence.
            links[:] = [link for link in links if not (link.purpose != 'local_guard' and
                (link.message_id == entry.source_message_id if entry.source_message_id else digest(source_by_id.get(link.message_id, '')) == entry.source_digest))]
        outcomes.append({'field': entry.field, 'revision': entry.revision, 'status': entry.action})
    if guard.risk == 'urgent': state.risk = 'urgent'
    state.family_unsafe |= guard.family_unsafe
    # Do not display a declined safety override as the final state's provenance.
    for field, protected in (('risk', guard.risk == 'urgent'), ('family_unsafe', guard.family_unsafe)):
        if protected:
            state.assessments = [a for a in state.assessments if a.field != field or a.value == str(getattr(state, field)).lower()]
    for outcome in outcomes:
        if (outcome['field'] == 'risk' and guard.risk == 'urgent') or (outcome['field'] == 'family_unsafe' and guard.family_unsafe):
            outcome['independent_guard_preserved'] = True
    return outcomes


def review_targets(req, state, links):
    by_id = dict(sources(req))
    targets = []
    for field in VALUES:
        assessment = next((a for a in reversed(state.assessments) if a.field == field), None)
        # Safety guard has its own local source; withdrawal cannot hide it.
        link = next((link for link in links if link.purpose == 'local_guard'), None) if field in ('risk', 'family_unsafe') else None
        message_id = assessment.message_id if assessment else link.message_id if link else req.message_id or f'current:{len(req.history)}'
        text = by_id.get(message_id, req.message)
        key = digest(text)
        explicit_ids = {m.message_id for m in req.history if m.role == 'user' and m.message_id} | ({req.message_id} if req.message_id else set())
        source_message_id = message_id if message_id in explicit_ids else None
        previous = next((r for r in reduce_reviews(req.reviews) if review_key(r) == (field, source_message_id or key)), None)
        targets.append(ReviewEntry(field=field, value=str(getattr(state, field)).lower(), action=previous.action if previous else 'confirm',
            source_message_id=source_message_id, source_digest=key, source_text=text, revision=previous.revision if previous else 0).model_dump())
    return targets
