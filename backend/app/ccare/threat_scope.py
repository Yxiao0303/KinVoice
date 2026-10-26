"""Explicit physical-threat evidence scopes shared by legacy and added guards.
Narrow lexical baseline: no calibrated probabilities or general coreference claim.
"""
from dataclasses import dataclass
import re
from typing import Protocol

QUOTES=re.compile(r'“[^”]*”|「[^」]*」|"[^"]*"')
PRESENT=re.compile(r'现在|此刻|正在|这会儿|目前')
PAST=re.compile(r'昨天|去年|以前|当时|曾经|刚才')
REPORTER=re.compile(r'(朋友(?:小[\u4e00-\u9fff])?|姐姐|室友|同事|哥哥)(?:说|告诉我|表示)\s*$')
RESOLUTION=re.compile(r'(?:她|他|朋友|姐姐|室友|同事|哥哥)(?:现在)?(?:已经|已)(?:安全到家|安全到校|到安全地方)')

@dataclass(frozen=True)
class QuoteScope:
    start:int
    end:int
    speaker:str
    target:str
    temporal:str
    resolved:bool
    basis:str

class ThreatScopeJudge(Protocol):
    """Future semantic adapter must cite spans; unknown cannot authorize exclusion."""
    def quote_scopes(self,text:str)->list[QuoteScope]: ...

class RuleThreatScopeJudge:
    def quote_scopes(self,text):
        scopes=[]
        for sentence in re.finditer(r'[^。！？；\n]+',text):
            part=sentence.group()
            for q in QUOTES.finditer(part):
                prefix,tail=part[:q.start()],part[q.end():]
                reporter=REPORTER.search(prefix)
                speaker,target,basis='unknown','unknown','unresolved_quote_role'
                resolved=False
                if reporter:
                    speaker=reporter.group(1);target='reported_speaker'
                    basis='explicit_other_report'
                    # One named reporter, one quote and no switch to another subject.
                    # Resolution must immediately follow the quote, not a distant clause.
                    resolution_text=tail.lstrip('，, ').strip()
                    if not resolution_text:
                        # One immediately following whole sentence, without intervening entities.
                        following=re.match(r'[。！？；\n]+([^。！？；\n]+)',text[sentence.end():])
                        resolution_text=following.group(1).strip() if following else ''
                    resolution=RESOLUTION.fullmatch(resolution_text)
                    if resolution and len(list(QUOTES.finditer(part)))==1:
                        subject=re.match(r'她|他|朋友|姐姐|室友|同事|哥哥',resolution.group()).group()
                        allowed_pronouns=('她',) if speaker=='姐姐' else ('他',) if speaker=='哥哥' else ('她','他')
                        resolved=subject in (speaker,*allowed_pronouns) and not re.search(r'朋友|姐姐|室友|同事|哥哥',prefix[:reporter.start()])
                elif not re.search(r'如果|假如|假设|剧本|小说|排练',prefix) and re.search(r'(?:对方|那个人)(?:对我)?说\s*$',prefix) and re.search(r'我(?:现在|此刻|正在)?被堵在[^，。]{0,8}门口',prefix):
                    speaker='aggressor';target='user';basis='blocked_user_and_direct_aggressor_speech'
                times=[(m.start(),'current') for m in PRESENT.finditer(prefix)]+[(m.start(),'historical') for m in PAST.finditer(prefix)]
                temporal=max(times)[1] if times else 'unknown'
                if resolved:temporal='resolved'
                scopes.append(QuoteScope(sentence.start()+q.start(),sentence.start()+q.end(),speaker,target,temporal,resolved,basis))
        return scopes


def physical_resolution_excludes(text,match):
    # Never exclude self-harm, overdose or unrelated current evidence.
    if not re.fullmatch(r'正在.{0,6}(?:打我|掐我|伤害我)',match.group()):return False
    return any(q.start<=match.start() and match.end()<=q.end and q.target=='reported_speaker' and q.resolved
               for q in RuleThreatScopeJudge().quote_scopes(text))


def postposed_current(tail):
    # Bind only an immediate event-anaphoric clause, not arbitrary later 'now'.
    return bool(re.match(r'\s*[，,]\s*(?:这|这件事|这一切)(?:就)?(?:发生在|正在发生(?:在)?)(?:现在|此刻)',tail))
