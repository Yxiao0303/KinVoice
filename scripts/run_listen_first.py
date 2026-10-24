"""Frozen offline paired action experiment. No external providers or credentials."""
import hashlib,json,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.ccare.schemas import TurnRequest
from selective_evidence import selective
from listen_first import choose,score
BUNDLE=ROOT/'research/listen-first-v1'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def hashes():
    paths=[Path(__file__),ROOT/'scripts/listen_first.py',ROOT/'scripts/selective_evidence.py',BUNDLE/'PLAN.md',
           ROOT/'research/selective-v1/frozen/linear.json',ROOT/'research/selective-v1/frozen/manifest.json',
           ROOT/'backend/app/ccare/engine.py',ROOT/'backend/app/ccare/policy.py']
    return {str(p.relative_to(ROOT)):sha(p) for p in paths}
def run():
    freeze=json.loads((BUNDLE/'freeze.json').read_text());lock=json.loads((BUNDLE/'data-lock.json').read_text())
    if freeze['hashes']!=hashes() or sha(BUNDLE/'cases.jsonl')!=lock['data_sha256'] or sha(BUNDLE/'freeze.json')!=lock['freeze_sha256']:
        raise ValueError('Frozen method or cases changed')
    cases=[json.loads(line) for line in (BUNDLE/'cases.jsonl').read_text().splitlines()]
    old=[]
    for p in [ROOT/'research/training-v1/data.jsonl',ROOT/'research/selective-v1/evaluation.jsonl']:
        old.extend(json.loads(l) for l in p.read_text().splitlines())
    for key in ('family_id','template_id'):
        if {r[key] for r in cases}&{r[key] for r in old}:raise ValueError('Family/template leakage')
    if len({c['case_id'] for c in cases})!=len(cases):raise ValueError('Duplicate cases')
    if any(c['synthetic'] is not True or c['review_status']!='unreviewed' for c in cases):raise ValueError('Unsupported provenance')
    out=BUNDLE/'results';out.mkdir(exist_ok=False)
    model=json.loads((ROOT/'research/selective-v1/frozen/linear.json').read_text())
    threshold=json.loads((ROOT/'research/selective-v1/frozen/manifest.json').read_text())['threshold']
    all_rows=[];reports={}
    for policy in ('old_selective','listen_first'):
        rows=[]
        for c in cases:
            req=TurnRequest.model_validate(c['request']);evidence=selective(model,req.message,threshold)
            result=choose(req,evidence['prediction'],policy)
            rows.append({'case_id':c['case_id'],'policy':policy,'gold':c['gold'],
                'evidence_prediction':evidence['prediction'],'output':result})
        reports[policy]=score(rows);all_rows.extend(rows)
    (out/'rows.json').write_text(json.dumps(all_rows,ensure_ascii=False,indent=2)+'\n')
    (out/'report.json').write_text(json.dumps({'created_utc':datetime.now(timezone.utc).isoformat(),
        'freeze':freeze,'data_lock':lock,'external_calls':0,'metrics':reports},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(reports,ensure_ascii=False))
if __name__=='__main__':run()
