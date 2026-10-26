"""CPU-only research proposals. No online routing, clinical labels or probability claim.
Reuses the existing character-bigram representation; all fitted parameters are saved.
"""
from collections import Counter
import math,random
from .learned_evidence import features
from .intent_scope import scoped_current_intent

LABELS=('listen','draft','clarify','unknown')
SEED=20261026
THRESHOLDS=(0.0,0.25,0.5,1.0,2.0)

def fit(rows):
    if not rows or any(r['split']!='train' or r['label'] not in LABELS for r in rows):raise ValueError('train_only')
    vocab=sorted({f for r in rows for f in features(r['text'])});counts={l:Counter() for l in LABELS};docs=Counter()
    for r in rows:counts[r['label']].update(features(r['text']));docs[r['label']]+=1
    nb={'kind':'multinomial_nb_char2','labels':LABELS,'alpha':1.0,'vocabulary':vocab,'documents':dict(docs),'counts':{l:dict(sorted(c.items())) for l,c in counts.items()}}
    model={'kind':'perceptron_char2_l2','labels':LABELS,'vocabulary':vocab,'weights':{l:{} for l in LABELS},'bias':{l:0.0 for l in LABELS},'seed':SEED,'epochs':25,'training_log':[]}
    rng=random.Random(SEED)
    for epoch in range(model['epochs']):
        indices=list(range(len(rows)));rng.shuffle(indices);updates=0
        for i in indices:
            row=rows[i];x=vector(row['text'],vocab);pred=output(model,row['text'])[0]
            if pred!=row['label']:
                updates+=1
                for label,sign in ((row['label'],1),(pred,-1)):
                    model['bias'][label]+=sign
                    for k,v in x.items():model['weights'][label][k]=model['weights'][label].get(k,0)+sign*v
        model['training_log'].append({'epoch':epoch+1,'updates':updates})
    return nb,model

def vector(text,vocabulary):
    vocab=set(vocabulary);x={k:float(v) for k,v in features(text).items() if k in vocab}
    norm=math.sqrt(sum(v*v for v in x.values()))
    return {k:v/norm for k,v in x.items()} if norm else {}

def output(model,text):
    if model['kind']=='multinomial_nb_char2':
        x=features(text);vocab=set(model['vocabulary']);scores={}
        for l in LABELS:
            counts=model['counts'][l];den=sum(counts.values())+len(vocab)
            scores[l]=math.log((model['documents'].get(l,0)+1)/(sum(model['documents'].values())+len(LABELS)))+sum(n*math.log((counts.get(f,0)+1)/den) for f,n in x.items() if f in vocab)
        known=bool(set(x)&vocab)
    else:
        x=vector(text,model['vocabulary']);known=bool(x)
        scores={l:model['bias'][l]+sum(model['weights'][l].get(k,0)*v for k,v in x.items()) for l in LABELS}
    order=sorted(LABELS,key=lambda l:scores[l],reverse=True)
    return order[0],scores[order[0]]-scores[order[1]],known

def rule(text):
    value=scoped_current_intent(text).value
    return value if value in LABELS else 'unknown'

def selective(model,text,threshold,scope=True):
    label,gap,known=output(model,text);current=scoped_current_intent(text)
    if scope and current.value in LABELS and current.value!='unknown':
        return {'prediction':current.value,'raw_label':label,'margin':gap,'reason':'explicit_scope_rule'}
    reason='scope_uncertain' if scope and current.blocks_inferred else 'no_features' if not known else 'low_margin' if gap<threshold else 'learned_proposal'
    return {'prediction':label if reason=='learned_proposal' else 'abstain','raw_label':label,'margin':gap,'reason':reason}

def metrics(rows,predictions):
    if not rows or len(rows)!=len(predictions):raise ValueError('paired_nonempty_required')
    matrix={l:{p:0 for p in (*LABELS,'abstain')} for l in LABELS}
    for row,p in zip(rows,predictions):matrix[row['label']][p]+=1
    n=len(rows);accepted=sum(p!='abstain' for p in predictions);correct=sum(r['label']==p for r,p in zip(rows,predictions));errors=accepted-correct
    return {'n':n,'accepted':accepted,'coverage':accepted/n,'abstentions':n-accepted,'selective_errors':errors,'selective_error_rate':errors/accepted if accepted else None,'correct_over_all':correct/n,'confusion_gold_rows':matrix,
            'unknown_correct':matrix['unknown']['unknown'],'unknown_n':sum(r['label']=='unknown' for r in rows),
            'explicit_requests_abstained':sum(p=='abstain' and r['label']!='unknown' for r,p in zip(rows,predictions))}

def choose_threshold(model,dev):
    if not dev or any(r['split']!='dev' for r in dev):raise ValueError('dev_only')
    grid=[]
    for threshold in THRESHOLDS:
        m=metrics(dev,[selective(model,r['text'],threshold)['prediction'] for r in dev])
        grid.append({'threshold':threshold,'loss':m['selective_errors']+.25*m['abstentions'],'feasible':m['coverage']>=.5,**m})
    candidates=[x for x in grid if x['feasible']]
    selected=min(candidates or grid,key=lambda x:(x['loss'],-x['coverage'],x['threshold']))
    return selected['threshold'],grid,bool(candidates)

class ResearchIntentAdapter:
    """Explicitly opt-in research interface; neither State nor Policy is mutated."""
    def __init__(self,model,threshold):self.model,self.threshold=model,threshold
    def propose(self,req):
        from .engine import local_state
        if local_state(req).risk=='urgent':return {'prediction':'abstain','reason':'independent_safety_priority'}
        if req.reviews:return {'prediction':'abstain','reason':'user_revision_priority'}
        return selective(self.model,req.message,self.threshold)|{'authority':'research_proposal_only'}
