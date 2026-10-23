"""Offline paired policy diagnostics; does not measure model or clinical efficacy."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.ccare.engine import local_state
from app.ccare.policy import decide, locate
from app.ccare.schemas import TurnRequest


def main():
    dirty=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True,encoding='utf-8').strip()
    if dirty: raise SystemExit('Commit reviewed changes before running the recorded diagnostics.')
    source=ROOT/'data/development/policy_pairs_v1.json'
    dataset=json.loads(source.read_text(encoding='utf-8'))
    rows=[]
    for pair in dataset['pairs']:
        observed=[]
        for arm in ('a','b'):
            case=pair[arm]
            req=TurnRequest(message=case['message'],history=case.get('history',[]),goal=case['goal'],eligible=True)
            state=local_state(req)
            policy=decide(req,state,[locate(req,q,'local_guard') for q in state.evidence])
            observed.append(policy.selected)
            rows.append({'pair_id':pair['id'],'arm':arm,'expected':case['expected'],'observed':policy.selected,'match':case['expected']==policy.selected,'decision':policy.model_dump()})
    run=ROOT/'experiments'/('policy-pairs-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    run.mkdir(parents=True,exist_ok=False)
    passed=sum(all(r['match'] for r in rows if r['pair_id']==p['id']) for p in dataset['pairs'])
    manifest={'kind':'development_policy_pairs_not_model_results','commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'dataset_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'pairs':len(dataset['pairs']),'cases':len(rows),'both_arms_match':passed,
        'external_model_calls':0,'success_criteria':'Both arms match prewritten developer expectations; exploratory engineering diagnostic only.',
        'limitations':['Used during implementation, not held out','No expert labels','No generated replies or model comparison','Pair construction does not prove causal effect in real conversations']}
    (run/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (run/'results.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n',encoding='utf-8')
    print(json.dumps({'record':str(run),'pairs':len(dataset['pairs']),'both_arms_match':passed,'external_model_calls':0}))


if __name__=='__main__': main()
