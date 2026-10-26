"""One-way local train -> freeze -> candidate lock -> evaluation. No network."""
import argparse,hashlib,json,platform,sys,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.ccare.student_intent_model import fit,output,selective,rule,metrics,choose_threshold,SEED
B=ROOT/'research/student-intent-p2-v1'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def load(name):return [json.loads(line) for line in (B/(name+'.jsonl')).read_text().splitlines()]
def hashes():
    names=['backend/app/ccare/student_intent_model.py','backend/app/ccare/intent_scope.py','backend/app/ccare/learned_evidence.py','scripts/train_student_intent.py','research/student-intent-p2-v1/PROTOCOL.md','research/student-intent-p2-v1/train.jsonl','research/student-intent-p2-v1/dev.jsonl']
    return {p:sha(ROOT/p) for p in names}
def check(rows):
    if len({r['id'] for r in rows})!=len(rows) or len({r['text'] for r in rows})!=len(rows):raise ValueError('duplicate_id_or_text')
    for key in ('family','template_family'):
        partition={}
        for r in rows:
            if not r['synthetic'] or r['review_status']!='unreviewed':raise ValueError('synthetic_only')
            if partition.setdefault(r[key],r['split'])!=r['split']:raise ValueError('group_leak')
    def trigrams(t):return {t[i:i+3] for i in range(len(t)-2)}
    pairs=[]
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            if a['split']==b['split']:continue
            x,y=trigrams(a['text']),trigrams(b['text']);sim=len(x&y)/len(x|y) if x|y else 1
            pairs.append((sim,a['id'],b['id']))
    nearest=sorted(pairs,reverse=True)[:10]
    if nearest and nearest[0][0]>=.85:raise ValueError('cross_split_near_duplicate')
    return {'max_cross_split_char3_jaccard':nearest[0][0] if nearest else None,'nearest_pairs':nearest,'threshold':.85,'note':'lexical audit only; shared intent grammar is not independent authorship'}
def prepare():
    rows=load('train')+load('dev');quality=check(rows)
    start=time.perf_counter();nb,linear=fit(load('train'));duration=time.perf_counter()-start
    tau,grid,feasible=choose_threshold(linear,load('dev'))
    folder=B/'frozen';folder.mkdir(exist_ok=False)
    dump(folder/'nb.json',nb);dump(folder/'linear.json',linear)
    dump(folder/'manifest.json',{'created_utc':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),'platform':platform.platform(),'seed':SEED,'train_n':len(load('train')),'dev_n':len(load('dev')),'training_seconds':duration,'threshold':tau,'threshold_grid':grid,'coverage_constraint_feasible':feasible,'hashes':hashes(),'models':{f:sha(folder/f) for f in ('nb.json','linear.json')},'quality':quality,'external_calls':0})
    print(json.dumps({'training_seconds':duration,'threshold':tau,'feasible':feasible}))
def verify():
    m=json.loads((B/'frozen/manifest.json').read_text())
    if m['hashes']!=hashes() or any(sha(B/'frozen'/p)!=v for p,v in m['models'].items()):raise ValueError('frozen_method_changed')
    return m

def lock():
    verify();rows=load('candidate')
    if any(r['split']!='candidate' for r in rows):raise ValueError('candidate_only')
    quality=check(load('train')+load('dev')+rows)
    with (B/'candidate-lock.json').open('x') as f:json.dump({'locked_utc':datetime.now(timezone.utc).isoformat(),'candidate_sha256':sha(B/'candidate.jsonl'),'frozen_sha256':sha(B/'frozen/manifest.json'),'quality':quality},f,ensure_ascii=False,indent=2)

def evaluate():
    m=verify();lock=json.loads((B/'candidate-lock.json').read_text())
    if sha(B/'candidate.jsonl')!=lock['candidate_sha256'] or sha(B/'frozen/manifest.json')!=lock['frozen_sha256']:raise ValueError('candidate_lock_changed')
    out=B/'results';out.mkdir(exist_ok=False)
    nb=json.loads((B/'frozen/nb.json').read_text());linear=json.loads((B/'frozen/linear.json').read_text())
    records=[];summary={}
    for split in ('train','dev','candidate'):
        rows=load(split);summary[split]={}
        for method in ('strong_rule','nb','linear','selective_hybrid','margin_only'):
            preds=[];start=time.perf_counter()
            for r in rows:
                if method=='strong_rule':d={'prediction':rule(r['text']),'reason':'scoped_rule'}
                elif method in ('nb','linear'):
                    label,gap,known=output(nb if method=='nb' else linear,r['text']);d={'prediction':label,'margin':gap,'known_features':known}
                else:d=selective(linear,r['text'],m['threshold'],scope=method=='selective_hybrid')
                preds.append(d['prediction']);records.append({'split':split,'method':method,'id':r['id'],'family':r['family'],'gold':r['label'],**d})
            summary[split][method]=metrics(rows,preds)|{'elapsed_seconds':time.perf_counter()-start}
    dump(out/'predictions.json',records);dump(out/'metrics.json',summary)
    dump(out/'receipt.json',{'evaluated_utc':datetime.now(timezone.utc).isoformat(),'frozen_manifest_sha256':sha(B/'frozen/manifest.json'),'candidate_lock_sha256':sha(B/'candidate-lock.json'),'predictions_sha256':sha(out/'predictions.json'),'metrics_sha256':sha(out/'metrics.json'),'paid_calls':0,'same_author_candidate_not_independent':True})
    print(json.dumps(summary['candidate'],ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','lock','evaluate','verify']);a=p.parse_args()
    {'prepare':prepare,'lock':lock,'evaluate':evaluate,'verify':verify}[a.phase]()
