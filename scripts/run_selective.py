"""Prepare/freeze before new synthetic evaluation data; never invokes a model API."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
from datetime import datetime,timezone
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.ccare.learned_evidence import fit,predict
from selective_evidence import fit_linear,choose_threshold,linear_output,selective,measurements
from train_evidence import load_data
BUNDLE=ROOT/'research/selective-v1'
OLD=ROOT/'research/training-v1/data.jsonl'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def timestamp():return datetime.now(timezone.utc).isoformat()
def hashes():
    paths=[Path(__file__),ROOT/'scripts/selective_evidence.py',BUNDLE/'PLAN.md',OLD,
           ROOT/'backend/app/ccare/learned_evidence.py',ROOT/'scripts/train_evidence.py']
    return {str(p.relative_to(ROOT)):sha(p) for p in paths}
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def prepare():
    path=BUNDLE/'frozen';path.mkdir(exist_ok=False)
    rows=load_data(OLD);train=[r for r in rows if r['split']=='train'];dev=[r for r in rows if r['split']=='dev']
    start=perf_counter();nb=fit(train);nb_seconds=perf_counter()-start
    start=perf_counter();linear=fit_linear(train);linear_seconds=perf_counter()-start
    tau,grid,feasible=choose_threshold(linear,dev)
    dump(path/'nb.json',nb);dump(path/'linear.json',linear)
    dump(path/'manifest.json',{'created_utc':timestamp(),'python':platform.python_version(),'seed':20261024,
        'train_n':len(train),'dev_n':len(dev),'old_exposed_diagnostic_n':6,
        'training_seconds':{'nb':nb_seconds,'linear':linear_seconds},'threshold':tau,
        'threshold_search':grid,'dev_constraint_feasible':feasible,'hashes':hashes(),
        'models':{name:sha(path/name) for name in ('nb.json','linear.json')},'external_calls':0})
    print(json.dumps({'threshold':tau,'dev_constraint_feasible':feasible,'training_seconds':linear_seconds}))

def evaluate():
    frozen=BUNDLE/'frozen';manifest=json.loads((frozen/'manifest.json').read_text())
    if manifest['hashes']!=hashes() or any(sha(frozen/name)!=digest for name,digest in manifest['models'].items()):
        raise ValueError('Frozen method or model changed')
    lock=json.loads((BUNDLE/'evaluation-lock.json').read_text())
    if lock['dataset_sha256']!=sha(BUNDLE/'evaluation.jsonl') or lock['frozen_manifest_sha256']!=sha(frozen/'manifest.json'):
        raise ValueError('Evaluation lock mismatch')
    new=load_data(BUNDLE/'evaluation.jsonl');old=load_data(OLD)
    for key in ('family_id','template_id','case_id'):
        if {r[key] for r in old}&{r[key] for r in new}:raise ValueError('New evaluation family/template/ID leakage')
    if any(r['split']!='test' for r in new):raise ValueError('New locked evaluation only')
    out=BUNDLE/'results';out.mkdir(exist_ok=False)
    nb=json.loads((frozen/'nb.json').read_text());linear=json.loads((frozen/'linear.json').read_text());tau=manifest['threshold']
    records=[];report={}
    for group,rows in [('old_exposed_diagnostic',[r for r in old if r['split']=='test']),('new_exploration',new)]:
        report[group]={}
        for method in ('nb','linear','selective','cue_only','margin_only'):
            predictions=[];raw=[]
            for row in rows:
                start=perf_counter()
                if method=='nb':
                    p=predict(nb,row['text']);result={'raw_label':p,'prediction':p,'reasons':[]}
                elif method=='linear':
                    p,gap,_=linear_output(linear,row['text']);result={'raw_label':p,'prediction':p,'margin':gap,'reasons':[]}
                else:result=selective(linear,row['text'],tau,cues=method!='margin_only',margin=method!='cue_only')
                records.append({'group':group,'method':method,'case_id':row['case_id'],'gold':row['label'],**result,
                    'elapsed_ms':(perf_counter()-start)*1000})
                predictions.append(result['prediction']);raw.append(result['raw_label'])
            gold=[r['label'] for r in rows]
            report[group][method]={'final':measurements(gold,predictions),'raw_three_class':measurements(gold,raw)}
    dump(out/'predictions.json',records)
    dump(out/'report.json',{'evaluated_utc':timestamp(),'frozen_manifest_sha256':sha(frozen/'manifest.json'),
        'evaluation_lock':lock,'external_calls':0,'metrics':report})
    print(json.dumps({m:v['final'] for m,v in report['new_exploration'].items()},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=['prepare','evaluate']);args=parser.parse_args()
    prepare() if args.phase=='prepare' else evaluate()
