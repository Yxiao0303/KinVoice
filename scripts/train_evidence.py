"""Offline, stdlib-only fitting with frozen family/template split; no model API."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import random
import sys
from time import perf_counter
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.ccare.learned_evidence import LABELS,fit,predict
from app.ccare.research import ContextRuleBaseline,Claim
from app.ccare.schemas import TurnRequest
BUNDLE=ROOT/'research/training-v1'


def hashes():
    paths=[BUNDLE/'data.jsonl', BUNDLE/'PLAN.md',Path(__file__),
        ROOT/'backend/app/ccare/learned_evidence.py',ROOT/'backend/app/ccare/research.py',ROOT/'backend/app/ccare/semantics.py']
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def load_data(path):
    rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    families,templates,ids={},{},set()
    for r in rows:
        if r['case_id'] in ids or r['label'] not in LABELS or r['split'] not in ('train','dev','test'):
            raise ValueError('Invalid ID/label/split')
        if r['synthetic'] is not True or r['review_status'] != 'unreviewed':
            raise ValueError('Unsupported data provenance')
        ids.add(r['case_id'])
        for registry,key in ((families,'family_id'),(templates,'template_id')):
            if r[key] in registry and registry[r[key]] != r['split']:
                raise ValueError('Family/template leakage')
            registry[r[key]]=r['split']
    return rows


def metrics(gold,pred):
    matrix={a:{b:0 for b in LABELS} for a in LABELS}
    for a,b in zip(gold,pred):matrix[a][b]+=1
    f1=[]
    for label in LABELS:
        tp=matrix[label][label];fp=sum(matrix[x][label] for x in LABELS if x!=label)
        fn=sum(matrix[label][x] for x in LABELS if x!=label)
        f1.append(2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0)
    return {'n':len(gold),'accuracy':sum(a==b for a,b in zip(gold,pred))/len(gold),
        'macro_f1':sum(f1)/3,'confusion_gold_rows':matrix}


def run(output):
    if hashes()!=json.loads((BUNDLE/'freeze.json').read_text()):
        raise ValueError('Frozen plan/data/implementation changed')
    rows=load_data(BUNDLE/'data.jsonl');train=[r for r in rows if r['split']=='train']
    output.mkdir(parents=True,exist_ok=False)
    random.seed(20261024)  # estimator itself deterministic, no stochastic optimizer
    tick=perf_counter();model=fit(train);training_seconds=perf_counter()-tick
    encoded=json.dumps(model,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    (output/'model.json').write_text(encoded)
    majority=max(LABELS,key=lambda x:sum(r['label']==x for r in train))
    records=[];summary={}
    for split in ('train','dev','test'):
        subset=[r for r in rows if r['split']==split];summary[split]={}
        for method in ('majority','rule','trained_char2_nb'):
            predictions=[]
            for r in subset:
                if method=='majority':label=majority
                elif method=='rule':
                    req=TurnRequest(message=r['text'],message_id='now')
                    label=ContextRuleBaseline().assess(req,Claim(field='support_intent',value='listen',message_id='now',quote=r['text'])).verdict
                else:label=predict(model,r['text'])
                predictions.append(label)
                records.append({'case_id':r['case_id'],'split':split,'method':method,'gold':r['label'],
                    'prediction':label,'error':label!=r['label']})
            summary[split][method]=metrics([r['label'] for r in subset],predictions)
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'seed':20261024,'python':platform.python_version(),
        'training_seconds':training_seconds,'samples':dict(Counter(r['split'] for r in rows)),
        'families':{s:len({r['family_id'] for r in rows if r['split']==s}) for s in ('train','dev','test')},
        'estimator':'multinomial naive Bayes; character bigrams; alpha=1; deterministic',
        'model_sha256':hashlib.sha256(encoded.encode()).hexdigest(),'frozen_hashes':hashes(),
        'external_calls':0,'metrics':summary,'limitations':'Developer synthetic, unreviewed, tiny held-out templates; no independent/clinical/generalization claim. Test used once; no tuning.'}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (output/'predictions.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'training_seconds':training_seconds,'samples':report['samples'],'test':summary['test']},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
