"""Narrow lexical assertion guard, not semantic entailment or calibrated affect detection.
Only explicit current first-person self-reports license corresponding affect words.
Unknown state alone neither licenses attribution nor prohibits neutral listening.
"""
import re
from .intent_scope import QUOTES, HISTORICAL, ATTRIBUTED

GROUPS = (
    r'难过|伤心|悲伤|失落|低落|沮丧|委屈',
    r'生气|愤怒|气愤|恼火',
    r'害怕|恐惧|恐慌',
    r'难受|不好受|心里堵得慌',
    r'悬着|忐忑|不安(?!全)|焦虑',
)
NEGATION = re.compile(r'不|没|并非|不是')
ASSERTION = re.compile(r'你|这种|这样的|这份|确实|一定|显然|听起来|听上去')


def unsupported_emotion(text, req):
    """Returns a reason, not a quality score. Quote/conditional replies are abstained.
    Conservative false positives remain possible; no attempt to infer latent emotion.
    """
    source = QUOTES.sub(lambda m: ' '*len(m.group()), req.message)
    reports = []
    for clause in re.split(r'[，。！？；,!?;\n]', source):
        if ((re.fullmatch(r'(?:很|有点|确实)?(?:'+ '|'.join(GROUPS) +r')',clause.strip()) or re.search(r'我(?:现在|此刻|确实|真的|感觉|觉得|有点|很|心里|也|仍|还)', clause))
                and not HISTORICAL.search(clause) and not ATTRIBUTED.search(clause)
                and not re.search(r'如果|假如|可能会|不是我', clause)):
            reports.append(clause)
    for clause in re.split(r'[，。！？；,!?;\n]', QUOTES.sub('', text)):
        if re.fullmatch(r'你(?:没有|没|并未)说(?:自己)?(?:'+ '|'.join(GROUPS) +r')',clause.strip()):
            continue
        if not ASSERTION.search(clause) or re.search(r'如果|是否|吗|可能|也许|不确定|不会再用', clause):
            continue
        for pattern in GROUPS:
            if not re.search(pattern, clause):
                continue
            supported = False
            for report in reports:
                for match in re.finditer(pattern, report):
                    if (re.fullmatch(r'(?:很|有点|确实)?',report[:match.start()].strip()) or
                        re.search(r'我(?:(?:现在|此刻|确实|真的|感觉|觉得|有点|很|心里|也|仍|还|感到))*$',report[:match.start()])):
                        supported = True
            # Negating a feeling also asserts knowledge; self-report does not
            # license reversing its polarity.
            match = re.search(pattern, clause)
            if not supported or NEGATION.search(clause[max(0,match.start()-4):match.start()]):
                return ['unsupported_emotion_assertion']
    return []
