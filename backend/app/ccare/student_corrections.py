"""Narrow, auditable speech-attribution corrections, not general coreference.
Runs after source validation and explicit UI revisions; never edits risk history.
"""
import re
from .reviews import sources

ACTORS={'我爸':'father','爸爸':'father','我妈':'mother','妈妈':'mother','老师':'teacher','同学':'peer','室友':'peer'}
CORRECTION=re.compile(r'(?:更正[：:]?)?(?:(?P<deictic>那句话|刚才那句话|刚才说的那句话)|[“「](?P<quote>[^”」]{2,100})[”」])是(?P<actor>我爸|爸爸|我妈|妈妈|老师|同学|室友)说的[。！]?')
SPEECH=re.compile(r'(?:我爸|爸爸|我妈|妈妈|老师|同学|室友)(?:说|告诉我)')

def field(event,name):return next(c for c in event.claims if c.field==name)

def retire(event,source_id):
    event.active=False
    for c in event.claims:
        c.value='unknown';c.status='revoked';c.evidence=[]
        c.supersedes=source_id+':student_subject' if source_id else None
        if not source_id:c.status='unknown'

def apply_natural_subject_corrections(req,judgment):
    from .student import link
    by_id=dict(sources(req));prior=[]
    for current in judgment.events:
        text=by_id[current.message_id];match=CORRECTION.fullmatch(text.strip())
        if not match:
            if ('那句话' in text and '说的' in text) or re.search(r'[“「].+[”」].{0,3}(?:不是|是).{0,10}说的',text):
                retire(current,None)
                judgment.uncertainties.append('该句可能是否定、假设或转述的纠正；不据此确定新主体，也不改动其他事件。')
            prior.append(current);continue
        candidates=[]
        for old in prior:
            original=by_id[old.message_id]
            # A message containing several statements/actors is not one linked
            # speech event. Do not pick the nearest merely because it is recent.
            single=(len(SPEECH.findall(original))==1 and len({v for k,v in ACTORS.items() if k in original})==1
                    and not re.search(r'假如|假设|如果|转述|朋友说|同学说|他告诉我|她告诉我',original) and not re.search(r'又说|还说|另外|另一件',original))
            if old.active and single and (not match['quote'] or match['quote'] in original):candidates.append(old)
        if len(candidates)!=1:
            # No binding is a scoped uncertainty, not a new factual event.
            retire(current,None)
            judgment.uncertainties.append('主体更正未能唯一绑定到一句原话；请用对应事件卡片更正，不据此改写其他事件。')
            prior.append(current);continue
        old=candidates[0]
        subject=field(current,'student_subject')
        explicit_status,explicit_value=subject.status,subject.value
        active=current.active
        # Invalidate every dependent claim rather than transplanting pressure,
        # impact or time onto the corrected speaker without supporting evidence.
        retire(old,current.event_id)
        for c in current.claims:
            c.value='unknown';c.status='unknown';c.evidence=[];c.supersedes=old.event_id+':'+c.field
        current.active=active
        if active:
            retained=field(current,'student_event');retained.value='retained';retained.status='supported'
            retained.evidence=[link(req,current.message_id,text)]
            if explicit_status!='revoked':
                subject.value=explicit_value if explicit_status=='confirmed' else ACTORS[match['actor']]
                subject.status='confirmed';subject.evidence=[link(req,current.message_id,text)]
            else:subject.status='revoked'
        else:
            # A revoked correction is a tombstone, not permission to resurrect
            # the old attribution. Source text still reaches independent safety.
            for c in current.claims:c.status='revoked'
        judgment.uncertainties.append('已按可绑定的主体更正停用旧事件及依赖；压力、影响和时序不自动迁移给新主体。')
        prior.append(current)
