"""Narrow scoped rules for two development threat families, not a safety model.
Existing acute guards remain independent; excluded/unknown is never 'safe'.
"""
import re
from .threat_scope import RuleThreatScopeJudge, PRESENT, PAST, QUOTES, postposed_current

THREAT = re.compile(r'堵(?:着|住)?[^。！？；\n]{0,18}门[^。！？；\n]{0,12}(?:说要打我|要打我|威胁我)|砸(?:东西|物品)[^。！？；\n]{0,12}(?:拦住我|不让我离开)')
QUOTE = QUOTES
OTHER = re.compile(r'(?:朋友|姐姐|室友|同事|哥哥)(?:说|告诉我|表示)')
NEGATED = re.compile(r'(?:没有人|没人|并没有|没有|并未|不会|不再)(?:在[^，,]{0,8})?$')
RESOLVED = re.compile(r'(?:堵门的人|对方|那个人|家人)(?:现在)?(?:已经|已)(?:离开|停止)|(?:我已|我已经)到安全(?:地点|地方)')


def assess_current_threat(text):
    quotes=[m.span() for m in QUOTE.finditer(text)]
    rows=[]
    scopes=RuleThreatScopeJudge().quote_scopes(text)
    for sentence in re.finditer(r'[^。！？；\n]+',text):
        part=sentence.group()
        for match in THREAT.finditer(part):
            start,end=sentence.start()+match.start(),sentence.start()+match.end()
            prefix=part[:match.start()];tail=part[match.end():]
            clause=re.split('[，,]',prefix)[-1]
            attribution_prefix=clause if re.match(r'\s*(?:但|不过|但是)?我(?:现在|此刻|目前)',clause) else prefix
            subject='user';scope='current';reason='current_user_threat'
            if any(a<=start and end<=b for a,b in quotes):subject='quoted';scope='quoted';reason='quoted_not_current_claim'
            elif OTHER.search(attribution_prefix):subject='other_or_quoted';scope='reported';reason='attributed_report'
            elif re.search(r'如果|假如|假设|剧本|小说|排练',prefix):scope='hypothetical';reason='hypothetical_or_fiction'
            elif NEGATED.search(clause) and not re.search(r'不是没有|并非没有',clause):scope='negated';reason='explicit_negation'
            else:
                times=[(m.start(),'current') for m in PRESENT.finditer(prefix)]+[(m.start(),'historical') for m in PAST.finditer(prefix)]
                scope='current' if postposed_current(tail) else max(times)[1] if times else 'unknown'
                reason='current_user_threat' if scope=='current' else 'time_not_current'
                if RESOLVED.search(tail):scope='resolved';reason='explicit_same_sentence_resolution'
            rows.append({'start':start,'end':end,'quote':text[start:end],'subject':subject,'scope':scope,'acute':subject=='user' and scope=='current','reason':reason})
    for q in scopes:
        if q.speaker=='aggressor' and q.target=='user' and q.temporal=='current' and re.fullmatch(r'[“「"](?:我)?(?:要|会)打你[”」"]',text[q.start:q.end]):
            # The quote is a perpetrator's direct threat, not a user's request.
            rows.append({'start':q.start,'end':q.end,'quote':text[q.start:q.end],'subject':'user','scope':'current','acute':True,'reason':q.basis})
    return rows


def current_threat_state(message,history):
    current=assess_current_threat(message)
    prior=[r for text in history for r in assess_current_threat(text)]
    active=[r for r in current if r['acute']]
    # Exact explicit resolution can retire this added guard's prior threat only.
    # It cannot suppress any legacy acute evidence or a fresh current match.
    resolved=bool(re.search(r'(?:堵门的人|砸东西的人|拦住我的人)(?:现在)?(?:已经|已)(?:离开|停止)',message))
    prior_active=any(r['acute'] for r in prior) and not resolved
    return bool(active) or prior_active, bool(current or prior), [r['quote'] for r in active]+([r['quote'] for r in prior if r['acute']] if prior_active else [])
