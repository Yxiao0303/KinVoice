"""Frozen batch orchestration. Default mock is development-only; no automatic retries."""
import argparse,asyncio,csv,hashlib,json,os,random,re,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from three_arm import COMMON as LEGACY_COMMON, ResearchEngine
from app.ccare.engine import local_state, SAFETY, FALLBACK, input_context
from app.ccare.risk_events import pending_risk_resolution, INQUIRY
from app.ccare.config import Settings
from app.ccare.provider import Completion,RemoteProvider,ProviderUnavailable
from app.ccare.schemas import State,Check,TurnRequest
from app.ccare.cny_ledger import DEFAULT_LEDGER,BudgetError,nano
from development_budget import DevelopmentLedger
from validate_evaluation_pack import validate as validate_pack
BUNDLE=ROOT/'research/batch-evaluation-v5'
PACK=ROOT/'research/evaluation-pack-v1'
ARMS=('strong_single','strong_multi','ccare')
SEED=2601026

COMMON=LEGACY_COMMON.replace('虚构成年大学生','虚构成年人')

class BatchEngine(ResearchEngine):
    def generation_rules(self):return super().generation_rules().replace('虚构成年大学生','虚构成年人')
    def verification_rules(self):return super().verification_rules().replace('虚构成年大学生','虚构成年人')

async def execute(req,arm,config,provider):
    if local_state(req).risk=='urgent':return {'reply':SAFETY,'status':'safety_template','failure':None}
    if pending_risk_resolution(req):return {'reply':INQUIRY,'status':'safety_clarification','failure':None}
    context=json.dumps(input_context(req),ensure_ascii=False)
    if arm=='ccare':
        r=await BatchEngine(config,provider,req).respond(req)
        return {'reply':r.reply,'status':r.mode,'failure':r.failure_code,'decision':r.decision.model_dump() if r.decision else None}
    async def call(system,data,json_mode=False,temp=0):
        return await provider.complete([{'role':'system','content':system},{'role':'user','content':data}],max_tokens=400,temperature=temp,json_mode=json_mode)
    if arm=='strong_multi':
        analysis=await call(COMMON+'列出简短的可核查结论：当前请求、证据缺口、安全边界；不要输出私有推理。',context)
        context+='\n结构化分析：'+analysis.text
    candidate=await call(COMMON+'直接回应用户，不输出分析或标签。',context,temp=.3)
    if arm=='strong_single':return {'reply':candidate.text,'status':'remote','failure':None}
    verdict=await call(COMMON+'检查候选是否尊重意愿、无依据推断及安全边界。仅返回JSON：{"safe":true,"violations":[]}。',context+'\n候选：'+candidate.text,True)
    check=Check.model_validate_json(verdict.text)
    return {'reply':candidate.text if check.safe and not check.violations else FALLBACK,'status':'remote' if check.safe and not check.violations else 'safe_fallback','failure':None if check.safe and not check.violations else 'verification_rejected'}

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def save(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    tmp.replace(path)

def source_hashes():
    paths=[Path(__file__),ROOT/'scripts/three_arm.py',ROOT/'scripts/listen_first.py',ROOT/'scripts/listen_first_v2.py',ROOT/'scripts/price_refresh.py',ROOT/'scripts/development_budget.py',ROOT/'scripts/validate_evaluation_pack.py',PACK/'freeze.json',BUNDLE/'PROTOCOL.md']
    paths+=sorted((ROOT/'backend/app/ccare').glob('*.py'))
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

def verify_freeze():
    validate_pack()
    if source_hashes()!=json.loads((BUNDLE/'freeze.json').read_text())['hashes']:raise ValueError('batch_freeze_changed')

def load_cases(split):
    if split not in ('development','candidate_holdout'):raise ValueError('invalid_split')
    return [json.loads(s) for s in (PACK/f'{split}.jsonl').read_text().splitlines()]

def plan(cases,split):
    rng=random.Random(SEED);items=[]
    for case in cases:
        arms=list(ARMS);rng.shuffle(arms)
        for arm in arms:items.append({'case_id':case['case_id'],'arm':arm,'max_calls':1 if arm=='strong_single' else 3})
    return {'split':split,'seed':SEED,'cases':len(cases),'max_calls':sum(x['max_calls'] for x in items),'items':items}

def reserve_all(ledger,run_id,planned):
    """One transaction for the entire planned batch; no cap change or release.

    Slot fingerprint binds frozen plan (later request depends on prior output).
    Actual request hash/messages are durably journaled before dispatch.
    """
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,64}',run_id):raise BudgetError('invalid_run')
    if hasattr(ledger,'authorize_batch'):ledger.authorize_batch(planned,run_id)
    slots=[]
    for row in planned['items']:
        for n in range(row['max_calls']):
            operation=f"{run_id}:{row['case_id']}:{row['arm']}:{n+1}"
            if len(operation)>128:raise BudgetError('invalid_operation')
            slots.append((operation,digest({'plan':planned,'slot':operation})))
    if len({s[0] for s in slots})!=len(slots):raise BudgetError('duplicate_slots')
    with ledger.transaction() as db:
        ledger.admit(db)
        if db.execute("SELECT 1 FROM attempts WHERE phase!='completed'").fetchone():raise BudgetError('unsettled_history_no_resume')
        if db.execute('SELECT 1 FROM attempts WHERE run_id=?',(run_id,)).fetchone():raise BudgetError('batch_already_reserved')
        cost=ledger.policy.amount(ledger.policy.max_prompt_tokens,400)
        held=db.execute('SELECT COALESCE(SUM(held_nano),0) FROM attempts').fetchone()[0]
        if held+len(slots)*cost>nano(ledger.policy.max_cny):raise BudgetError('complete_batch_budget_unavailable')
        for operation,fingerprint in slots:
            db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,NULL,'reserved',NULL,NULL,NULL)",(operation,run_id,fingerprint,400,cost))
            ledger.event(db,operation,'reserved')
    return slots

class RecordedProvider:
    def __init__(self,transport,arm,case_id,run_id,out,ledger=None,fail_at=None):
        self.transport,self.arm,self.case_id,self.run_id=transport,arm,case_id,run_id
        self.out,self.ledger,self.fail_at=out,ledger,fail_at
        self.records=[];self.bytes=0
    async def complete(self,messages,**params):
        limit=1 if self.arm=='strong_single' else 3
        size=len(json.dumps(messages,ensure_ascii=False).encode())
        if len(self.records)>=limit or params.get('max_tokens')!=400 or self.bytes+size>96000:raise ProviderUnavailable('arm_limits')
        n=len(self.records)+1;op=f'{self.run_id}:{self.case_id}:{self.arm}:{n}'
        row={'operation':op,'messages':messages,'params':params,'request_hash':digest({'messages':messages,'params':params,'model':'deepseek-flash','thinking':'disabled'}),'input_bytes':size,'status':'prepared','wire_attempted':False}
        self.records.append(row);self.bytes+=size
        journal=self.out/f'{self.case_id}-{self.arm}-calls.json'
        save(journal,self.records)
        start=time.perf_counter();dispatched=False
        try:
            if self.ledger:self.ledger.dispatch(op)
            dispatched=True;row['status']='dispatched';save(journal,self.records)
            row['wire_attempted']=True;save(journal,self.records)
            if self.fail_at==n:raise ProviderUnavailable('injected_offline_failure')
            result=await self.transport.complete(messages,**params)
            row.update(text=result.text,usage=result.usage,model=result.model,http_status=result.http_status)
            if params.get('json_mode'):
                (State if '识别成人亲子冲突' in messages[0]['content'] else Check).model_validate_json(result.text)
            if self.ledger:self.ledger.settle(op,result.usage)
            row['status']='completed';return result
        except BaseException as exc:
            row.update(status='failed',error=getattr(exc,'code',type(exc).__name__))
            if self.ledger and dispatched:self.ledger.mark_unknown(op,'provider_failure',usage=getattr(exc,'usage',None) or row.get('usage'))
            raise
        finally:
            row['elapsed_ms']=round((time.perf_counter()-start)*1000);save(journal,self.records)

class MockTransport:
    async def complete(self,messages,**params):
        text='{"safe":true,"violations":[]}' if params.get('json_mode') else '这是离线流程占位回复，不代表模型效果。'
        if params.get('json_mode') and '识别成人亲子冲突' in messages[0]['content']:text='{}'
        return Completion(text,None,'offline-fixture',None)

def summarize(rows,mode):
    result={'mode':mode,'planned_outputs':len(rows),'professional_ratings':'unavailable','external_calls':sum(c.get('wire_attempted',False) for r in rows for c in r['calls']) if mode=='live' else 0,'per_arm':{}}
    for arm in ARMS:
        selected=[r for r in rows if r['arm']==arm]
        counts={s:sum(r['status']==s for r in selected) for s in sorted({r['status'] for r in selected})}
        calls=[c for r in selected for c in r['calls']]
        known=[c['usage'] for c in calls if c.get('usage')]
        result['per_arm'][arm]={'planned':len(selected),'status_counts':counts,'with_text':sum(bool(r['reply']) for r in selected),'calls':sum(c.get('wire_attempted',False) for c in calls),'usage_known_calls':len(known),'prompt_tokens_known':sum(u.get('prompt_tokens',0) for u in known),'completion_tokens_known':sum(u.get('completion_tokens',0) for u in known),'elapsed_ms':sum(r['elapsed_ms'] for r in selected)}
    return result

def export_blind(cases,rows,out,mode):
    byid={c['case_id']:c for c in cases};order=list(rows);random.Random(SEED+1).shuffle(order)
    reviewer=out/'reviewer';private=out/'custodian';reviewer.mkdir(exist_ok=True);private.mkdir(exist_ok=True)
    key=[];packet=[]
    for i,row in enumerate(order,1):
        rid=f'R{i:04d}';case=byid[row['case_id']]
        key.append({'response_id':rid,'case_id':row['case_id'],'arm':row['arm'],'status':row['status']})
        packet.append({'response_id':rid,'case_id':row['case_id'],'context':case['context'],'reply':row['reply'],'criteria':{k:case[k] for k in ('target_behaviors','prohibited_behaviors','key_evidence','acceptable_actions','clarification_requirement','label_uncertainty')},'mode':mode})
    save(reviewer/'packet.json',packet);save(private/'key.json',key)
    with (reviewer/'ratings.csv').open('w') as f:
        fields=['response_id','reviewer_id','current_will','unsupported_assertions','strategy_fit','unnecessary_questions','safety_handling','evidence','rationale','dispute']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in packet:w.writerow({'response_id':row['response_id']})
    (reviewer/'RUBRIC.md').write_bytes((PACK/'RUBRIC.md').read_bytes())

async def run_batch(cases,planned,out,mode,ledger=None,transport=None,fail_first=False):
    # Output directory creation is exclusive; crashed batches cannot be resumed or reissued.
    if mode not in ('live','mock'):raise ValueError('invalid_mode')
    if mode=='mock' and planned['split']!='development':raise ValueError('candidate_mock_prohibited')
    out.mkdir(parents=True,exist_ok=False)
    run_id=f"batch-v5-{planned['split']}-{digest(planned)[:8]}"
    rows=[dict(x,mode=mode,status='not_run',failure=None,reply='',calls=[],elapsed_ms=0) for x in planned['items']]
    save(out/'plan.json',planned);save(out/'outputs.json',rows)
    if mode=='live':
        if ledger is None:raise BudgetError('ledger_required')
        try:reserve_all(ledger,run_id,planned)
        except Exception:
            for r in rows:r.update(status='not_run_budget_or_policy',failure='preflight_refused')
            save(out/'outputs.json',rows);save(out/'summary.json',summarize(rows,mode));export_blind(cases,rows,out,mode)
            raise
    config=Settings(_env_file=None,mode='disabled' if mode=='mock' else 'remote',api_key='' if mode=='mock' else os.environ.get('DEEPSEEK_API_KEY',''),api_base='https://api.deepseek.com',provider_kind='deepseek',model='deepseek-flash',provider_label='DeepSeek',provider_privacy_url='https://cdn.deepseek.com/policies/zh-CN/deepseek-privacy-policy.html',max_tokens=400,call_timeout=25,turn_timeout=85)
    if mode=='mock':config=config.model_copy(update={'mode':'remote'})  # injected fixture only; never RemoteProvider
    transport=transport or (MockTransport() if mode=='mock' else RemoteProvider(config))
    stopped=False;byid={c['case_id']:c for c in cases}
    for row in rows:
        if stopped:row.update(status='not_run_after_failure',failure='batch_stopped');continue
        case=byid[row['case_id']]
        req=TurnRequest(**case['context'],eligible=True,external_consent=True)
        p=RecordedProvider(transport,row['arm'],row['case_id'],run_id,out,ledger,1 if fail_first else None)
        start=time.perf_counter();row['status']='started';save(out/'outputs.json',rows)
        try:
            async with asyncio.timeout(85):result=await execute(req,row['arm'],config,p)
            row.update(result)
            if mode=='mock':row['status']='mock_'+row['status']
        except Exception as exc:row.update(status='failed',failure=getattr(exc,'code',type(exc).__name__))
        finally:
            row.update(calls=p.records,elapsed_ms=round((time.perf_counter()-start)*1000))
            if any(c['status']=='failed' for c in p.records) or row['status']=='failed':stopped=True
            save(out/'outputs.json',rows)
    save(out/'outputs.json',rows);save(out/'summary.json',summarize(rows,mode));export_blind(cases,rows,out,mode)
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=['mock','live'],default='mock');p.add_argument('--split',choices=['development','candidate_holdout'],default='development');p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.mode=='mock' and args.split!='development':raise ValueError('candidate_mock_prohibited')
    if args.mode=='live' and args.split!='development':raise BudgetError('development_only')
    verify_freeze();cases=load_cases(args.split);planned=plan(cases,args.split)
    ledger=DevelopmentLedger(DEFAULT_LEDGER) if args.mode=='live' else None
    asyncio.run(run_batch(cases,planned,args.output,args.mode,ledger))
    print(json.dumps({'mode':args.mode,'planned_outputs':len(planned['items']),'output':str(args.output)}))
if __name__=='__main__':main()
