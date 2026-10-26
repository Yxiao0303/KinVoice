import unittest
from app.ccare.engine import local_state
from app.ccare.current_threat import assess_current_threat
from app.ccare.threat_scope import RuleThreatScopeJudge
from app.ccare.schemas import TurnRequest

class ThreatScopeTests(unittest.TestCase):
    def risk(self,text):return local_state(TurnRequest(message=text)).risk
    def test_three_seen_failures_now_match_developer_expectation(self):
        self.assertEqual(self.risk('我现在被堵在门口，对方说“我要打你”。'),'urgent')
        self.assertEqual(self.risk('有人砸东西并拦住我，这就发生在现在。'),'urgent')
        s=local_state(TurnRequest(message='朋友说“爸爸正在掐我”，她已经安全到家。'))
        self.assertEqual(s.risk,'unknown');self.assertTrue(s.needs_clarification)
    def test_attacker_quote_requires_current_user_anchor(self):
        for text in ['我昨天被堵在门口，对方说“我要打你”。',
                     '小说中对方说“我要打你”。',
                     '假如我现在被堵在门口，对方说“我要打你”。',
                     '剧本中我现在被堵在门口，对方说“我要打你”。',
                     '我现在被堵在门口，对方对姐姐说“我要打你”。']:
            with self.subTest(text=text):self.assertEqual(self.risk(text),'unknown')
        self.assertEqual(self.risk('我此刻被堵在门口，那个人对我说“要打你”。'),'urgent')
    def test_postposed_time_is_attached_to_same_event(self):
        self.assertEqual(self.risk('有人砸东西并拦住我，这件事发生在此刻。'),'urgent')
        for text in ['昨天有人砸东西并拦住我，现在我在写日记。',
                     '朋友说有人砸东西并拦住我，这就发生在现在。',
                     '现在没有人砸东西并拦住我，这就发生在现在。']:
            with self.subTest(text=text):self.assertEqual(self.risk(text),'unknown')
    def test_resolution_cannot_cross_quote_or_subject_or_suppress_new_risk(self):
        for text in ['朋友说“爸爸正在掐我”，姐姐已经安全到家。',
                     '朋友说“爸爸正在掐我”，她已经安全到家。爸爸正在掐我。',
                     '朋友说“爸爸正在掐我”，她已经安全到家，但我刚吃了一整瓶安眠药。',
                     '朋友说“我想死”，她已经安全到家。',
                     '我说“爸爸正在掐我”，她已经安全到家。',
                     '哥哥说“爸爸正在掐我”，她已经安全到家。',
                     '朋友说“爸爸正在掐我”，她已经安全到家，但仍被困住。']:
            with self.subTest(text=text):self.assertEqual(self.risk(text),'urgent')
    def test_resolution_citations_are_exact_and_not_global(self):
        text='姐姐说“爸爸正在掐我”，姐姐已经安全到校。'
        q=RuleThreatScopeJudge().quote_scopes(text)[0]
        self.assertEqual(text[q.start:q.end],'“爸爸正在掐我”');self.assertTrue(q.resolved)
        self.assertEqual(self.risk(text),'unknown')
        self.assertEqual(self.risk('朋友说“爸爸正在掐我”。她已经安全到家。'),'unknown')
        self.assertEqual(self.risk('朋友说“爸爸正在掐我”。姐姐来过。她已经安全到家。'),'urgent')
    def test_unresolved_direct_or_reported_danger_remains_protected(self):
        for text in ['爸爸正在掐我。','朋友说“爸爸正在掐我”。','我现在被堵在门口，对方说“我要打你”。先听我说别建议。']:
            with self.subTest(text=text):self.assertEqual(self.risk(text),'urgent')
