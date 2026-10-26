"""Research artifact and boundary tests; never call a provider or old holdout."""
import copy,hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from app.ccare.student_intent_model import fit,output,metrics,ResearchIntentAdapter,choose_threshold
from app.ccare.schemas import TurnRequest,ReviewEntry
from app.ccare.student import respond_student
from app.ccare.student_schemas import StudentRequest,StudentProfile
from train_student_intent import B,load,verify,check

class StudentIntentModelTests(unittest.TestCase):
    def test_frozen_method_models_and_split_audit(self):
        m=verify();self.assertEqual((m['train_n'],m['dev_n']),(32,12))
        self.assertEqual(m['seed'],20261026)
        rows=load('train')+load('dev')+load('candidate')
        self.assertEqual(len(rows),60);check(rows)
        lock=json.loads((B/'candidate-lock.json').read_text())
        self.assertEqual(hashlib.sha256((B/'candidate.jsonl').read_bytes()).hexdigest(),lock['candidate_sha256'])
        receipt=json.loads((B/'results/receipt.json').read_text())
        for name in ('predictions','metrics'):
            self.assertEqual(hashlib.sha256((B/f'results/{name}.json').read_bytes()).hexdigest(),receipt[name+'_sha256'])
    def test_actual_fit_is_reproducible_and_train_only(self):
        nb,linear=fit(load('train'))
        self.assertEqual(json.loads(json.dumps(nb)),json.loads((B/'frozen/nb.json').read_text()))
        self.assertEqual(json.loads(json.dumps(linear)),json.loads((B/'frozen/linear.json').read_text()))
        self.assertTrue(any(x['updates'] for x in linear['training_log']))
        with self.assertRaises(ValueError):fit(load('candidate'))
        with self.assertRaises(ValueError):choose_threshold(linear,load('candidate'))
    def test_family_and_exact_duplicate_detection(self):
        rows=load('train');bad=copy.deepcopy(rows[0]);bad.update(id='bad',split='candidate',text='另一句话')
        with self.assertRaisesRegex(ValueError,'group_leak'):check(rows+[bad])
        with self.assertRaisesRegex(ValueError,'duplicate'):check(rows+[rows[0]])
    def test_all_predictions_denominators_and_abstention_not_success(self):
        records=json.loads((B/'results/predictions.json').read_text());self.assertEqual(len(records),60*5)
        rows=[{'label':'listen'},{'label':'unknown'}]
        result=metrics(rows,['abstain','abstain'])
        self.assertEqual(result['coverage'],0);self.assertIsNone(result['selective_error_rate']);self.assertEqual(result['correct_over_all'],0)
        summary=json.loads((B/'results/metrics.json').read_text())
        for method,m in summary['candidate'].items():
            self.assertEqual(m['n'],16)
            self.assertEqual(sum(sum(row.values()) for row in m['confusion_gold_rows'].values()),16)
    def test_research_adapter_cannot_take_over_safety_or_revision(self):
        m=verify();adapter=ResearchIntentAdapter(json.loads((B/'frozen/linear.json').read_text()),m['threshold'])
        self.assertEqual(adapter.propose(TurnRequest(message='爸爸正在掐我。'))['reason'],'independent_safety_priority')
        req=StudentRequest(message='这次考试后妈妈批评我。',message_id='u:1',student=StudentProfile(adult_confirmed=True))
        r=respond_student(req);t=next(t for t in r.review_targets if t['field']=='student_subject')
        revised=req.model_copy(update={'reviews':[ReviewEntry.model_validate(t|{'action':'correct','value':'father','revision':1})]})
        self.assertEqual(adapter.propose(revised)['reason'],'user_revision_priority')
        r2=respond_student(revised)
        self.assertEqual(next(c.value for c in r2.student_judgment.events[0].claims if c.field=='student_subject'),'father')
        plain=TurnRequest(message='帮我写一段话。');before=plain.model_dump();proposal=adapter.propose(plain)
        self.assertEqual(plain.model_dump(),before);self.assertEqual(proposal['authority'],'research_proposal_only')
    def test_p1_unknown_and_current_rejection_survive_menu_choice(self):
        for text in ['朋友说“我睡不着”。','昨天我睡不着。']:
            r=respond_student(StudentRequest(message=text,student=StudentProfile(adult_confirmed=True)))
            self.assertEqual(next(c.value for c in r.student_judgment.events[0].claims if c.field=='student_impact'),'unknown')
        req=StudentRequest(message='考试后先听我说，不要给我计划。',support='small_step',student=StudentProfile(adult_confirmed=True))
        self.assertEqual(respond_student(req).strategy,'listen')
