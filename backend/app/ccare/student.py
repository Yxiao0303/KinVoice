"""Offline P1: evidence -> source-scoped revision -> constrained support.
Not a trained classifier or clinically validated student assessment. One source
message is one unresolved event container; multiple events are never auto-merged.
"""
import re
from .schemas import EvidenceLink, PolicyDecision, ReviewEntry
from .student_schemas import StudentClaim, StudentEvent, StudentJudgment, StudentResponse
from .reviews import sources, digest, reduce_reviews, apply_reviews, review_targets
from .engine import local_state, SAFETY
from .policy import decide, locate
from .intent_scope import scoped_current_intent, QUOTES
from .risk_events import pending_risk_resolution, INQUIRY

FIELDS = {
    'student_pressure': ('unknown','academic','family','academic_family','peer','future'),
    'student_subject': ('unknown','self','mother','father','teacher','peer','multiple'),
    'student_time': ('unknown','current','past','future'),
    'student_impact': ('unknown','study','sleep','daily','multiple'),
    'student_event': ('unknown','retained'),
}
STAGES = {
    'middle': {'design_only':True,'focus':'学习适应、作业与家庭期待','support':'安全时可找可信任的成年人；不默认联系涉事家长。'},
    'high': {'design_only':True,'focus':'考试、备考节奏与升学信息','support':'整理可控事项与待核实信息，不替学生决定选科或升学。'},
    'university': {'design_only':False,'focus':'成人学业受挫与家庭期待','support':'先核对事件和当前需要，提供可拒绝的小步骤或措辞。'},
}
PRESSURE = {'academic':r'考试|作业|课程|复习|成绩|挂科','family':r'妈妈|爸爸|我妈|我爸|父母|家里|家人',
            'peer':r'同学|室友|同伴','future':r'升学|选科|实习|就业|专业选择'}
SUBJECT = {'mother':r'妈妈|我妈','father':r'爸爸|我爸','teacher':r'老师','peer':r'同学|室友'}
IMPACT = {'study':r'我(?:最近|这几天|现在)?(?:学不进去|看不进(?:书|教材)|(?:没法|无法|不能|难以)(?:学习|复习|上课|做作业))',
          'sleep':r'我(?:最近|这几天|现在)?(?:睡不着|失眠|没睡好)',
          'daily':r'我(?:最近|这几天|现在)?(?:吃不下|不想出门|无法出门)'}


def link(req, mid, text, purpose='state'):
    current=mid==(req.message_id or f'current:{len(req.history)}')
    turn=len(req.history) if current else next(i for i,m in enumerate(req.history) if (m.message_id or f'history:{i}')==mid)
    return EvidenceLink(message_id=mid,source='current' if current else 'history',turn=turn,start=0,end=len(text),quote=text,purpose=purpose)

class RuleStudentJudge:
    def extract(self,req):
        events=[]
        for mid,text in sources(req):
            evidence=link(req,mid,text)
            hypothetical=bool(re.search(r'假如|假设|如果',text))
            reported=bool(re.search(r'朋友说|同学说|他告诉我|她告诉我|转述',text))
            # Quotes and attribution can hide scope: keep unknown, never read
            # quoted symptoms as the user's own functioning or current needs.
            ambiguous=hypothetical or reported
            kinds=[k for k,p in PRESSURE.items() if re.search(p,text)]
            pressure='academic_family' if set(kinds)=={'academic','family'} else kinds[0] if len(kinds)==1 else 'unknown'
            subjects=[k for k,p in SUBJECT.items() if re.search(p,text)]
            subject=subjects[0] if len(subjects)==1 else 'multiple' if len(subjects)>1 else 'self' if text.startswith('我') else 'unknown'
            times=[v for v,p in [('past',r'昨天|以前|曾经|上周'),('current',r'今天|现在|这次|正在'),('future',r'明天|下周|以后')] if re.search(p,text)]
            tense=times[0] if len(times)==1 else 'unknown'
            impacts=[k for k,p in IMPACT.items() if re.search(p,text)]
            impact=impacts[0] if len(impacts)==1 else 'multiple' if len(impacts)>1 else 'unknown'
            if ambiguous or re.search(r'[“”「」"]|不是|并非|以前|曾经|昨天',text):impact='unknown'
            values={'student_pressure':pressure if not hypothetical else 'unknown',
                    'student_subject':subject if not ambiguous else 'unknown',
                    'student_time':tense if not hypothetical else 'unknown',
                    'student_impact':impact,'student_event':'retained'}
            event=StudentEvent(event_id='student-event:'+digest(mid+':'+digest(text))[:24],message_id=mid,source_digest=digest(text),
                provenance='hypothetical' if hypothetical else 'reported' if reported else 'self_report',
                claims=[StudentClaim(field=f,value=v,status='supported' if v!='unknown' else 'unknown',evidence=[evidence] if v!='unknown' else []) for f,v in values.items()])
            events.append(event)
        return StudentJudgment(stage=req.student.stage,events=events,
            uncertainties=['未表达的影响及持续时间保持未知；未知不要求逐项追问。',
                           '主体/时态为保守词面判断；同一消息多事件或跨消息指代不自动合并。'])


def apply_student_reviews(req, judgment):
    for event in judgment.events:
        for review in reduce_reviews(req.reviews):
            if review.field not in FIELDS or (review.source_message_id!=event.message_id if review.source_message_id else review.source_digest!=event.source_digest):continue
            claim=next(c for c in event.claims if c.field==review.field)
            claim.value='unknown' if review.action=='revoke' else review.value
            claim.status='revoked' if review.action=='revoke' else 'confirmed'
            claim.revision=review.revision;claim.supersedes=event.event_id+':'+claim.field+':'+str(review.revision-1)
            claim.evidence=[link(req,event.message_id,dict(sources(req))[event.message_id])] if review.action!='revoke' else []
        retained=next(c for c in event.claims if c.field=='student_event')
        if retained.status=='revoked' or retained.value=='unknown':
            event.active=False
            for c in event.claims:
                if c.field!='student_event':
                    c.value='unknown';c.status='revoked';c.evidence=[];c.supersedes=event.event_id+':student_event'


def student_targets(req, judgment):
    by_id=dict(sources(req));targets=[]
    if not judgment.events:return targets
    # Latest meaningful event remains correctable on a neutral follow-up.
    meaningful=[e for e in judgment.events if any(c.value!='unknown' and c.field!='student_event' for c in e.claims)]
    chosen=meaningful[-1] if meaningful else judgment.events[-1]
    for c in chosen.claims:
        previous=next((r for r in reduce_reviews(req.reviews) if r.field==c.field and
            (r.source_message_id==chosen.message_id if r.source_message_id else r.source_digest==chosen.source_digest)),None)
        explicit_ids={m.message_id for m in req.history}|{req.message_id}
        targets.append(ReviewEntry(field=c.field,value=c.value,action=previous.action if previous else 'confirm',
            source_message_id=chosen.message_id if chosen.message_id in explicit_ids else None,
            source_digest=chosen.source_digest,source_text=by_id[chosen.message_id],revision=previous.revision if previous else 0).model_dump())
    return targets


def extract_validated(req, judge):
    judgment=(judge or RuleStudentJudge()).extract(req)
    # Adapter output must be typed and all evidence must map to unchanged user text.
    judgment=StudentJudgment.model_validate(judgment.model_dump())
    by_id=dict(sources(req))
    if len(judgment.events)!=len(by_id) or {e.message_id for e in judgment.events}!=set(by_id):raise ValueError("student_event_coverage_invalid")
    for e in judgment.events:
        if e.message_id not in by_id or e.source_digest!=digest(by_id[e.message_id]):raise ValueError('student_source_mismatch')
        if not e.active:raise ValueError('adapter_cannot_revoke_event')
        if e.event_id!='student-event:'+digest(e.message_id+':'+e.source_digest)[:24]:raise ValueError('student_event_id_invalid')
        if {c.field for c in e.claims}!=set(FIELDS) or len(e.claims)!=len(FIELDS):raise ValueError('student_fields_incomplete')
        for c in e.claims:
            if c.status not in ('supported','unknown') or c.revision or c.supersedes:raise ValueError('adapter_cannot_author_reviews')
            if c.status=='unknown' and c.value!='unknown':raise ValueError('student_unknown_invalid')
            if c.value not in FIELDS[c.field]:raise ValueError('student_value_invalid')
            if c.status in ('supported','confirmed') and c.value!='unknown' and not c.evidence:raise ValueError('student_evidence_required')
            for ev in c.evidence:
                if ev.message_id!=e.message_id or ev.start<0 or ev.end<=ev.start or not ev.quote or ev!=link(req,e.message_id,by_id[e.message_id]):raise ValueError('student_evidence_mismatch')
    return judgment


def respond_student(req, *, judge=None):
    # Called only by the separate offline endpoint (or explicit synthetic tests).
    state=local_state(req);guard=state.model_copy(deep=True)
    local_links=[locate(req,q,'local_guard') for q in state.evidence]
    outcomes=apply_reviews(req,state,local_links,guard)
    failure=None
    try:judgment=extract_validated(req,judge)
    except (ValueError,TypeError,AttributeError):
        failure='student_judgment_invalid'
        judgment=StudentJudgment(stage=req.student.stage,events=[],uncertainties=['本轮判断未通过结构或来源检查；不展示未经核对的结论。'])
    apply_student_reviews(req,judgment)
    from .student_corrections import apply_natural_subject_corrections
    apply_natural_subject_corrections(req,judgment)
    decision=decide(req,state,local_links)
    current=scoped_current_intent(req.message)
    action=decision.selected if decision.allowed in (['safety'],['clarify'],['listen']) or current.value!='unknown' or 'current_text_intent' in decision.reasons else req.support
    if action not in ('safety','clarify') and current.blocks_inferred:action='listen'
    if action=='draft' and state.family_unsafe:action='listen'
    # Do not turn a recognized word into a high-impact recommendation.
    if action not in ('listen','safety') and re.search(r'替我决定|帮我决定|直接选',req.message):action='options'
    # A task-specific refusal outranks the menu. A later explicit revision can reopen it.
    current_text=re.split(r'但现在|现在改为|我改主意了|更正[：:]?',QUOTES.sub('',req.message))[-1]
    refused_task=bool(re.search(r'(?:不要|不想|先别)[^。！？，]{0,8}(?:计划|步骤|建议|写)',current_text))
    if action not in ('safety','clarify') and refused_task:action='listen'
    if action=='draft' and not re.search(r'明天|稍后|暂停|晚点|再谈|请教|错题',req.message):action='clarify'
    if failure and action!='safety':action='listen'
    judgment.current_need=current.value if current.value!='unknown' else state.support_intent if state.support_intent!='unknown' else req.support
    judgment.need_origin='explicit_text' if current.value!='unknown' else 'review' if state.support_intent!='unknown' else 'user_choice'
    if current.value!='unknown':
        ev=link(req,req.message_id or f'current:{len(req.history)}',req.message,'intent')
        ev.start=current.start;ev.end=current.end;ev.quote=req.message[current.start:current.end]
        judgment.need_evidence=[ev]
    if refused_task:
        judgment.current_need='listen';judgment.need_origin='explicit_text'
        judgment.need_evidence=[link(req,req.message_id or f'current:{len(req.history)}',req.message,'intent')]
    judgment.action=action;judgment.risk=state.risk
    judgment.reasons=decision.reasons+['offline_student_rules','current_request_or_explicit_support_choice']
    judgment.basis_event_ids=[e.event_id for e in judgment.events if e.active and any(c.value!='unknown' and c.field!='student_event' for c in e.claims)]
    replies={
        'listen':'我在听。你可以先说完，不需要马上给出计划，也不用补齐所有信息。',
        'organize':'我们可以分开整理：已经发生的事、你自己想做的事、还需要核实的信息。卡片里的未知项可以先留着，你可以纠正其中任何一项。',
        'clarify':'为了完成你请求的帮助，你最需要先确认的是哪一个对象或哪一项具体要求？只说明这一点就可以。',
        'draft':'可以这样写：“这件事我想'+('明天再谈' if '明天' in req.message else '稍后再谈')+'，先让我把自己的想法整理好。”这只是可修改的草稿，不会替你发送。',
        'small_step':'可选的小步骤：从你提到的学习任务里选一项，把第一步缩小到十分钟能开始的程度，做完再决定是否继续。你也可以缩小或放弃这一步；它不保证成绩提高。',
        'options':'我不会替你决定升学或就业。可以列出你愿意考虑的选项、自己的偏好、仍需核实的信息，再决定是否找合适的人讨论；没有可靠来源的政策或岗位信息先留空。',
        'ground':'如果愿意，可以先暂停一下，感受脚踩地面的触感。不舒服就停，不需要完成练习。',
        'safety':SAFETY,
    }
    if action=='draft' and re.search(r'请教|错题',req.message):replies['draft']='可以这样写：“老师您好，我想请教一下这次学习中还没弄懂的地方，您方便时可以帮我看看吗？”你可以补充具体题目，也可以不用这段话。'
    reply=INQUIRY if pending_risk_resolution(req) and state.risk!='urgent' else replies[action]
    if failure and action!='safety':reply='本轮判断没有通过检查，暂不据此提出具体建议。你可以暂停、纠正或重新说明想得到的帮助。'
    if req.student.stage!='university':reply+='（仅适龄设计样例：需要真人支持时，考虑安全且可信任的成年人或专业人员，不默认找涉事家长。）'
    policy=PolicyDecision(requested=req.support,selected=action,allowed=[action],reasons=judgment.reasons,evidence=decision.evidence)
    return StudentResponse(reply='[学生场景离线规则示例] '+reply,mode='safe_fallback' if failure and action!='safety' else 'demo',failure_code=failure,strategy=action,state=state,
        checks=['independent_local_guard','student_source_validation','offline_only_no_provider'],model_calls=0,usage=[],
        decision=policy,student_judgment=judgment,review_targets=review_targets(req,state,local_links)+student_targets(req,judgment),
        review_outcomes=outcomes+[{'field':r.field,'revision':r.revision,'status':r.action} for r in reduce_reviews(req.reviews) if r.field in FIELDS])
