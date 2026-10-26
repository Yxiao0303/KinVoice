"""Research-only revision; old frozen method remains untouched."""
import re
from listen_first import choose,LISTEN,ADVICE,DETAIL,SAFETY_QUESTION,MISSING,SAFETY_UNKNOWN,LISTEN_ONLY
from app.ccare.schemas import TurnRequest

ADVICE_REQUEST=re.compile(r'帮我[^。！？；，]{0,40}(?:写|选|比较|安排|制定|处理)|请[^。！？；，]{0,40}(?:建议|办法|步骤)|给我[^。！？；，]{0,40}(?:建议|方案|办法)|该怎么做')
NEGATED_REQUEST=re.compile(r'不是要你|并非要你|不需要你|不要你|不是请你|不想让你')
RESOLVED_OTHER=re.compile(r'(?:朋友|姐姐|室友)(?:说|表示|告诉我)[^。！？]{0,160}(?:已经|已)(?:安全到校|安全到家|到安全地方)[。！？]?')


def request_features(text):
    current=re.split(r'但现在|现在改为|更正[：:]?|我改主意了',text)[-1]
    clauses=re.split(r'[。！？；，]',current)
    explicit=any(ADVICE_REQUEST.search(c) and not NEGATED_REQUEST.search(c) for c in clauses)
    negated=any(NEGATED_REQUEST.search(c) for c in clauses)
    # Strip only an explicitly attributed and resolved span; retain later user risk.
    safety_text=RESOLVED_OTHER.sub('',text)
    return {'explicit_advice':explicit,'negated_request':negated,
            'listen_only':bool(LISTEN_ONLY.search(current)),
            'material_gap':bool(MISSING.search(current)),
            'safety_unknown':bool(SAFETY_UNKNOWN.search(safety_text))}


def choose_v2(req:TurnRequest,evidence_prediction='abstain'):
    # Original text always reaches independent acute guard, including attributed text.
    result=choose(req,evidence_prediction,'listen_first')
    if result['urgent_guard']:return result
    f=request_features(req.message)
    action,reply,reason='listen',LISTEN,'unknown_allowed_neutral_listening'
    if f['safety_unknown']:
        action,reply,reason='safety_question',SAFETY_QUESTION,'current_safety_information_missing'
    elif not f['listen_only'] and (f['explicit_advice'] or (req.goal=='draft' and not f['negated_request'])):
        if f['material_gap']:action,reply,reason='detail_question',DETAIL,'requested_advice_missing_referent'
        else:action,reply,reason='bounded_advice',ADVICE,'current_nonnegated_request'
    return result|{'action':action,'reply':reply,'reason':reason,'question':'？' in reply}
