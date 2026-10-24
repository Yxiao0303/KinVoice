"""Conservative, replaceable lexical evidence baseline; not calibrated entailment."""
import re
from typing import Protocol, Literal

Verdict = Literal['supported', 'contradicted', 'insufficient']

class SemanticJudge(Protocol):
    def assess(self, field: str, value: str, text: str) -> Verdict: ...

# Whole source is inspected: a quote fragment alone can conceal negation/attribution.
AMBIGUOUS = re.compile(r'[“”「」"《》]|他说|她说|朋友说|老师说|假如|如果|假设|反话|才怪|以前|昨天|曾经|并非不|不是不|没有不')
PATTERNS = {
    'listen': r'不要.{0,4}建议|别.{0,4}(?:建议|劝)|只.{0,5}(?:听我说|听听|倾听)|不想.{0,4}(?:沟通|和解|联系)|先别.{0,4}(?:建议|劝)',
    'draft': r'想.{0,6}(?:写段话|写一段|草稿|措辞)|帮我.{0,5}(?:写|表达)',
    'clarify': r'想.{0,4}(?:梳理|澄清|理清)',
    'ground': r'想.{0,4}(?:平静|稳定|冷静)',
    'sad': r'难过|伤心', 'angry': r'生气|愤怒', 'afraid': r'害怕|恐惧',
    'true': r'打我|掐我|威胁|监控|不让我走|暴力',
    'urgent': r'自杀|自残|想死|吞药|割腕|跳楼',
}

class RuleSemanticJudge:
    def assess(self, field, value, text):
        if AMBIGUOUS.search(text):
            return 'insufficient'
        pattern = PATTERNS.get(str(value))
        if not pattern:
            return 'insufficient'
        match = re.search(pattern, text)
        if not match:
            return 'insufficient'
        prefix = text[max(0, match.start()-6):match.start()]
        if re.search(r'(?:没有|并不|不是|不再|不想|不)(?:很|再|要|觉得)?$', prefix):
            return 'contradicted'
        return 'supported'


def current_intent(text):
    # Explicit correction revokes earlier wording within this turn.
    current = re.split(r'但现在|不过现在|现在改为|我改主意了|更正[：:]?', text)[-1]
    judge = RuleSemanticJudge()
    for value in ('listen', 'draft', 'clarify', 'ground'):
        if judge.assess('support_intent', value, current) == 'supported':
            return value
    return 'unknown'
