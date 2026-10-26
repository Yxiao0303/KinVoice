"""Conservative current-user intent scope rules, not a semantic entailment model."""
from dataclasses import dataclass
import re

@dataclass(frozen=True)
class ScopedIntent:
    value: str = 'unknown'
    start: int = 0
    end: int = 0
    blocks_inferred: bool = False

QUOTES=re.compile(r'“[^”]*”|「[^」]*」|"[^"]*"')
REVISION=re.compile(r'但现在|不过现在|现在改为|我改主意了|更正[：:]?|现在请')
ATTRIBUTED=re.compile(r'朋友(?:说|表示|希望|要求)|(?:他|她|爸爸|妈妈|老师|姐姐|室友)(?:说|表示|告诉)|(?:他|她)希望')
HISTORICAL=re.compile(r'以前|昨天|曾经|当时|过去')
FUTURE=re.compile(r'之后|以后|然后|稍后|等.{0,8}再|再(?:给|帮|提|想)')
SELF=re.compile(r'^\s*(?:但|不过)?\s*我(?:现在|此刻|只|想|要|不|先|希望|并|还)')
NEGATED=re.compile(r'(?:不是|并非|并不|不再|不要|不想|不需要)(?:要|想|让|请)?(?:你)?\s*$')
PATTERNS={
 'listen':re.compile(r'不要.{0,4}建议|先别.{0,4}(?:建议|劝)|别.{0,4}(?:建议|劝)|只.{0,5}(?:听我说|听听|倾听)|先听我(?:说|讲)|只想(?:说说|倾诉)|不想.{0,4}(?:沟通|和解|联系)'),
 'draft':re.compile(r'想.{0,6}(?:写段话|写一段|草稿|措辞)|(?:帮我|替我).{0,12}(?:写|表达)|(?:想要|需要|请给我|给我)(?:一|几)(?:句|段)[^。！？；，]{0,16}(?:说明|话|措辞|回复)|(?:想|准备)(?:给[^。！？；，]{0,8})?(?:写|发)(?:一句|一段)'),
 'clarify':re.compile(r'(?:请|先)(?:先)?(?:确认|问清|核实)|想.{0,4}(?:梳理|澄清|理清)|(?:请|给我)[^。！？；，]{0,40}(?:建议|办法|步骤)'),
 'ground':re.compile(r'想.{0,4}(?:平静|稳定|冷静)'),
}


def scoped_current_intent(text):
    # Mask, do not delete: evidence offsets still index the original message.
    masked=QUOTES.sub(lambda m:' '*len(m.group()),text)
    revisions=list(REVISION.finditer(masked));offset=revisions[-1].end() if revisions else 0
    # '现在请' keeps 请 for the general advice recognizer.
    if revisions and revisions[-1].group()=='现在请':offset-=1
    hits=[];blocked=bool(QUOTES.search(text));attributed=False;historical=False
    for sentence in re.finditer(r'[^。！？；;\n]+',masked[offset:]):
        attributed=historical=False
        for clause in re.finditer(r'[^，,]+',sentence.group()):
            part=clause.group();base=offset+sentence.start()+clause.start()
            if SELF.search(part):attributed=historical=False
            if ATTRIBUTED.search(part):attributed=True
            if HISTORICAL.search(part):historical=True
            # Explicit present pivot ends old tense/attribution within a clause.
            present=re.search(r'(?:但|不过)?(?:我)?(?:现在|此刻)',part)
            if present:
                base+=present.end();part=part[present.end():];historical=False
                if '我' in present.group():attributed=False
            if attributed or historical or re.search(r'如果|假如|假设|也许|要是',part):
                blocked=True
                continue
            future=FUTURE.search(part)
            if future:part=part[:future.start()]
            for value,pattern in PATTERNS.items():
                for match in pattern.finditer(part):
                    prefix=part[max(0,match.start()-10):match.start()]
                    if NEGATED.search(prefix):blocked=True;continue
                    # Advice inside an explicit refusal is not a second preference.
                    if value=='clarify' and re.search(r'不要|别|不需要|不是',prefix):continue
                    hits.append((value,base+match.start(),base+match.end()))
    values={v for v,_,_ in hits}
    # Without an explicit revision, a present listening/refusal constraint wins
    # over a simultaneous incompatible suggestion request. Do not infer state.
    if 'listen' in values:
        value,start,end=[hit for hit in hits if hit[0]=='listen'][-1]
        return ScopedIntent(value,start,end,blocked or len(values)>1)
    # A direct request to establish missing facts precedes composing wording.
    if values == {'draft', 'clarify'}:
        value,start,end=[hit for hit in hits if hit[0]=='clarify'][-1]
        return ScopedIntent(value,start,end,blocked)
    if len(values)!=1:return ScopedIntent(blocks_inferred=blocked or len(values)>1)
    value,start,end=hits[-1]
    return ScopedIntent(value,start,end,blocked)
