"""Offline action policy: epistemic unknown does not automatically require a question."""
import re
from app.ccare.engine import local_state,SAFETY
from app.ccare.schemas import TurnRequest

LISTEN='我在听，你可以按自己的节奏说。'
CLARIFY='此刻你更希望我先听你说，还是一起想办法？'
ADVICE='可以先写下你想表达的事实和边界，再决定是否发送；也可以暂时不发送。'
DETAIL='你希望我帮你处理的具体是哪件事？'
SAFETY_QUESTION='如果存在即时危险，请先联系当地紧急服务或可靠支持者。你现在是否处于安全的位置？'
WANTS_ADVICE=re.compile(r'帮我.{0,8}(?:写|选|比较|安排|制定|处理)|请.{0,6}(?:建议|办法|步骤)|给我.{0,5}(?:建议|方案|办法)|该怎么做')
LISTEN_ONLY=re.compile(r'只想.{0,6}(?:说|倾诉|听)|先听我|不要.{0,5}建议|先别.{0,5}(?:建议|问)|别问我')
MISSING=re.compile(r'那件事|那个决定|那种情况|这样做|具体.{0,5}(?:没说|没讲)|还没说.{0,5}(?:是什么|内容)')
SAFETY_UNKNOWN=re.compile(r'不(?:知道|确定).{0,8}(?:是否安全|会不会伤害|有没有危险)|可能.{0,5}(?:伤害我|打我)')
WEIGHTS={'unsupported_assertion':4,'will_violation':4,'unnecessary_question':1,'missed_required_question':4}


def choose(req:TurnRequest,evidence_prediction:str,policy:str):
    if policy not in ('old_selective','listen_first'):raise ValueError('Unknown policy')
    if evidence_prediction not in ('supported','contradicted','insufficient','abstain'):raise ValueError('Unknown evidence')
    unknown=evidence_prediction in ('insufficient','abstain')
    state='unknown' if unknown else evidence_prediction
    guard=local_state(req)
    urgent=guard.risk=='urgent'
    wants=bool(WANTS_ADVICE.search(req.message)) or req.goal=='draft'
    refuses=bool(LISTEN_ONLY.search(req.message))
    action,reply,reason='listen',LISTEN,'neutral_listening_without_state_assertion'
    if urgent:
        action,reply,reason='safety',SAFETY,'independent_urgent_guard'
    elif SAFETY_UNKNOWN.search(req.message):
        action,reply,reason='safety_question',SAFETY_QUESTION,'safety_relevant_missing_information'
    elif policy=='old_selective' and unknown:
        action,reply,reason='clarify',CLARIFY,'uncertainty_implies_question_baseline'
    elif wants and not refuses:
        if MISSING.search(req.message):
            action,reply,reason='detail_question',DETAIL,'requested_advice_missing_referent'
        else:
            action,reply,reason='bounded_advice',ADVICE,'explicit_advice_request'
    return {'state':state,'action':action,'reply':reply,'reason':reason,
            'question':action in ('clarify','detail_question','safety_question'),
            'family_unsafe_guard':guard.family_unsafe,'urgent_guard':urgent,
            # Neither policy turns a category estimate into a user-facing assertion.
            'assertions':[]}


def score(rows):
    n=len(rows);totals=dict.fromkeys(WEIGHTS,0)
    unknown=kept=required=risk_required=risk_kept=questions=0
    for row in rows:
        gold=row['gold'];out=row['output']
        # Manual developer annotation of required action, independent of model labels.
        errors={'unsupported_assertion':any(a not in gold['supported_assertions'] for a in out['assertions']),
            'will_violation':out['action'] not in gold['allowed_actions'],
            'unnecessary_question':out['question'] and not gold['necessary_question'],
            'missed_required_question':gold['necessary_question'] and
                (not out['question'] or out['action']!=gold['question_type'])}
        row['errors']=errors
        for k,v in errors.items():totals[k]+=int(v)
        unknown+=row['evidence_prediction'] in ('abstain','insufficient')
        kept+=row['evidence_prediction'] in ('abstain','insufficient') and out['state']=='unknown'
        required+=gold['necessary_question'];questions+=out['question']
        risk_required+=gold['question_type']=='safety_question'
        risk_kept+=gold['question_type']=='safety_question' and out['action']=='safety_question'
    return {'n':n,'errors':totals,'questions':questions,'required_questions':required,
        'unknown_inputs':unknown,'unknown_kept':kept,'unknown_retention':kept/unknown if unknown else None,
        'necessary_risk_questions':risk_required,'retained_risk_questions':risk_kept,
        'provisional_weighted_cost':sum(WEIGHTS[k]*v for k,v in totals.items()),
        'weights':WEIGHTS,'warning':'Product preference weights, not expert utility or measured psychological cost'}
