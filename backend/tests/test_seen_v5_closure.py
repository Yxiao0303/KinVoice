"""AI synthetic / unreviewed, seen-development counterexamples, not holdout evidence."""
import asyncio,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from three_arm import ActionSelector,ResearchEngine
from app.ccare.engine import local_state
from app.ccare.emotion_grounding import unsupported_emotion
from app.ccare.schemas import TurnRequest,State
from app.ccare.config import Settings
from app.ccare.provider import Completion

class SeenV5Closure(unittest.TestCase):
    def decision(self,text):
        req=TurnRequest(message=text)
        return ActionSelector().select(req,local_state(req),[])
    def test_current_request_priority(self):
        examples=[
            ('不需要你劝我改变决定，并不等于不需要措辞帮助。我决定不参加聚餐，想要一句不指责人的说明。','draft'),
            ('想请你替我写一句拒绝来访的话。对方可能是室友，也可能是房东。不同身份会影响语气，请先确认。','clarify'),
            ('请给我一句礼貌的回复。','draft'),
            ('我不需要你帮我写一段话。','listen'),
            ('先听我说，然后再帮我写一段话。','listen'),
            ('朋友希望你帮我写一段话。','listen'),
            ('朋友说“帮我写一段话”。','listen'),
            ('我不确定需要什么。','listen'),
            ('先听我说。但现在帮我写一段话。','draft'),
            ('爸爸正在掐我，先听我说。','safety'),
        ]
        for text,expected in examples:
            with self.subTest(text=text):self.assertEqual(self.decision(text).selected,expected)
    def test_unknown_is_preserved(self):
        req=TurnRequest(message='请给我一句礼貌的回复。');state=State()
        self.assertEqual(ActionSelector().select(req,state,[]).selected,'draft')
        self.assertEqual(state.emotion,'unknown');self.assertEqual(state.risk,'unknown')
    def test_affect_support_and_opposites(self):
        cases=[
            ('照片显示已读，他没回复。我不能确定什么意思。','这种悬着的感觉确实不好受。',True),
            ('我现在感觉不好受。','你现在不好受。',False),
            ('我现在很伤心。','你感到难过。',False),
            ('我现在不难过。','你感到难过。',True),
            ('朋友说“我现在很伤心”。','你很伤心。',True),
            ('我昨天很伤心。','你很伤心。',True),
            ('我现在很伤心。','你并不伤心。',True),
            ('我不知道该说什么。','我在听，你可以按自己的节奏说。',False),
            ('我现在很伤心。','你一定很生气。',True),
            ('我觉得爸爸很伤心。','你很伤心。',True),
            ('我没说自己难过。','你没说自己难过。',False),
            ('我不知道。','如果你身边不安全，请联系紧急服务。',False),
        ]
        for source,reply,reject in cases:
            with self.subTest(source=source,reply=reply):
                self.assertEqual(bool(unsupported_emotion(reply,TurnRequest(message=source))),reject)
    def test_engine_uses_final_strategy_and_rejects_unsupported_affect(self):
        class Fixture:
            def __init__(self):self.messages=[]
            async def complete(self,messages,**kw):
                self.messages.append(messages)
                return Completion('{}' if len(self.messages)==1 else '你一定很伤心。',None,'offline')
        req=TurnRequest(message='请给我一句礼貌的回复。',external_consent=True)
        cfg=Settings(_env_file=None,api_key='',mode='disabled').model_copy(update={'mode':'remote'})
        provider=Fixture();r=asyncio.run(ResearchEngine(cfg,provider,req).respond(req))
        self.assertEqual(r.decision.selected,'draft');self.assertEqual(r.mode,'safe_fallback')
        self.assertIn('unsupported_emotion_assertion',r.checks)
        self.assertIn('以最终strategy为准',provider.messages[1][0]['content'])
        self.assertEqual(len(provider.messages),2)
