"""Request-local event binding using existing source IDs, digests and evidence links.
Only explicitly reported physical harm is eligible. No general safety-history reset.
"""
from dataclasses import dataclass
import re
from .reviews import sources,digest,reduce_reviews
from .schemas import EvidenceLink
from .threat_scope import RuleThreatScopeJudge

PHYSICAL=re.compile(r'正在.{0,6}(?:打我|掐我|伤害我)')
RESOLVED=re.compile(r'(朋友(?:小[\u4e00-\u9fff])?|姐姐|室友|同事|哥哥|她|他)(?:现在)?(?:已经|已)(?:安全到家|安全到校|到安全地方)[。！]?')
INQUIRY='你说的已安全，是先前提到受伤害的同一个人、同一件事吗？如果仍有人正受到伤害，请先寻求当地紧急帮助。'

@dataclass
class RiskEventBinding:
    event_id:str
    subject:str
    source_digest:str
    evidence:EvidenceLink
    status:str='active'
    update_evidence:EvidenceLink|None=None
    review_revision:int|None=None


def bind_risk_events(req):
    eligible=sources(req);events=[]
    positions={m.message_id or f'history:{i}':i for i,m in enumerate(req.history) if m.role=='user'}
    positions[eligible[-1][0]]=len(req.history)
    for index,(mid,text) in enumerate(eligible):
        if index<len(eligible)-1:
            for q in RuleThreatScopeJudge().quote_scopes(text):
                if q.target!='reported_speaker' or q.resolved:continue
                for m in PHYSICAL.finditer(text,q.start,q.end):
                    evidence=EvidenceLink(message_id=mid,source='history',turn=positions[mid],start=m.start(),end=m.end(),quote=m.group(),purpose='local_guard')
                    event_id='risk-event:'+digest(f'{mid}:{digest(text)}:{m.start()}:{m.end()}')[:24]
                    events.append(RiskEventBinding(event_id,q.speaker,digest(text),evidence))
        apply_event_update(req,eligible[:index+1],events,mid,text,positions, index==len(eligible)-1)
    return events


def apply_event_update(req,eligible,events,mid,text,positions,current):
    # Replay user updates chronologically; assistant text is never in sources().
    update=RESOLVED.fullmatch(text.strip())
    if not update:return
    review_entries=[r for r in reduce_reviews(req.reviews) if r.field=='risk']
    update_reviews=[r for r in review_entries if (r.source_message_id==mid if r.source_message_id else r.source_digest==digest(text))]
    if any(r.action=='revoke' or (r.action=='correct' and r.value=='urgent') for r in update_reviews):return
    subject=update.group(1)
    linked=[e for e in events if e.status!='resolved' and (subject in ('她','他') or e.subject==subject)]
    if not linked:return
    evidence=EvidenceLink(message_id=mid,source='current' if current else 'history',turn=positions[mid],start=0,end=len(text),quote=text,purpose='local_guard')
    # Reviews disambiguate provenance only; never alone prove resolution.
    selected=[]
    for e in linked:
        reviews=[r for r in review_entries if (r.source_message_id==e.evidence.message_id if r.source_message_id else r.source_digest==e.source_digest)]
        if reviews:
            r=reviews[0]
            if r.action in ('confirm','correct') and r.value=='unknown':selected.append((e,r.revision))
    generic_ambiguous=subject=='朋友' and any(re.search(r'另一(?:位|个)朋友|两个朋友|几位朋友|朋友小[\u4e00-\u9fff]',t) for _,t in eligible[:-1])
    if subject not in ('她','他') and not generic_ambiguous and (len(linked)==1 or len(selected)==1):
        chosen=linked[0] if len(linked)==1 else selected[0][0]
        if sum(e.evidence.message_id==chosen.evidence.message_id for e in linked)==1:
            chosen.status='resolved';chosen.update_evidence=evidence
            chosen.review_revision=selected[0][1] if len(selected)==1 else None
            return
    for e in linked:e.status='pending_resolution';e.update_evidence=evidence


def pending_risk_resolution(req):
    return any(e.status=='pending_resolution' for e in bind_risk_events(req))
