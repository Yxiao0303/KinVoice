"""Offline CPU research: fitted linear scores and explicit abstention, not confidence."""
import math
import random
import re
from collections import Counter
from app.ccare.learned_evidence import LABELS,features

THRESHOLDS=(0.0,0.25,0.5,1.0,2.0)
CUES={
 'attribution':r'朋友|室友|她说|他说|姐姐|爸爸说|妈妈说|[“”「」"]',
 'time':r'以前|曾经|昨天|当时|过去',
 'missing_or_hypothetical':r'不知道|不确定|分不清|还没|如果|假如|也许',
 'revision_or_negation_scope':r'更正|改主意|改变想法|不是不|并非不',
}


def vector(text,vocabulary):
    observed={k:float(v) for k,v in features(text).items() if k in vocabulary}
    norm=math.sqrt(sum(v*v for v in observed.values()))
    return {k:v/norm for k,v in observed.items()} if norm else {}


def fit_linear(rows):
    if not rows or any(r['split']!='train' for r in rows):
        raise ValueError('Train partition only')
    vocabulary=sorted({f for r in rows for f in features(r['text'])})
    weights={label:{} for label in LABELS};bias={label:0.0 for label in LABELS}
    rng=random.Random(20261024);updates=[]
    for epoch in range(30):
        indices=list(range(len(rows)));rng.shuffle(indices);mistakes=0
        for i in indices:
            r=rows[i];x=vector(r['text'],set(vocabulary))
            scores={l:bias[l]+sum(weights[l].get(k,0)*v for k,v in x.items()) for l in LABELS}
            pred=max(LABELS,key=lambda l:scores[l]);gold=r['label']
            if pred!=gold:
                mistakes+=1
                for label,sign in ((gold,1),(pred,-1)):
                    bias[label]+=sign
                    for k,v in x.items():weights[label][k]=weights[label].get(k,0)+sign*v
        updates.append({'epoch':epoch+1,'updates':mistakes})
    return {'type':'multiclass_perceptron_char2_l2','seed':20261024,'epochs':30,
            'vocabulary':vocabulary,'weights':weights,'bias':bias,'training_log':updates}


def linear_output(model,text):
    x=vector(text,set(model['vocabulary']))
    scores={l:model['bias'][l]+sum(model['weights'][l].get(k,0)*v for k,v in x.items()) for l in LABELS}
    ordered=sorted(LABELS,key=lambda l:scores[l],reverse=True)
    return ordered[0],scores[ordered[0]]-scores[ordered[1]],bool(x)


def selective(model,text,threshold,*,cues=True,margin=True):
    label,gap,known=linear_output(model,text)
    reasons=[name for name,pattern in CUES.items() if cues and re.search(pattern,text)]
    if not known: reasons.append('no_known_features')
    if margin and gap<threshold: reasons.append('low_margin')
    return {'raw_label':label,'prediction':'abstain' if reasons else label,
            'margin':gap,'reasons':reasons,
            'action':'clarify' if reasons or label=='insufficient' else 'retain_candidate'}


def choose_threshold(model,dev):
    if not dev or any(r['split']!='dev' for r in dev):raise ValueError('Dev only')
    choices=[]
    for t in THRESHOLDS:
        pred=[selective(model,r['text'],t)['prediction'] for r in dev]
        accepted=[(r,p) for r,p in zip(dev,pred) if p!='abstain']
        errors=sum(r['label']!=p for r,p in accepted)
        choices.append({'threshold':t,'accepted':len(accepted),'errors':errors,
                        'feasible':len(accepted)>=2 and errors==0})
    feasible=[r for r in choices if r['feasible']]
    chosen=min(feasible,key=lambda r:(-r['accepted'],r['threshold']))['threshold'] if feasible else 0.0
    return chosen,choices,bool(feasible)


def measurements(gold,pred):
    if not gold or len(gold)!=len(pred):raise ValueError('Nonempty paired predictions required')
    if any(g not in LABELS for g in gold) or any(p not in (*LABELS,'abstain') for p in pred):raise ValueError('Invalid label')
    matrix={g:{p:0 for p in (*LABELS,'abstain')} for g in LABELS}
    for g,p in zip(gold,pred):matrix[g][p]+=1
    n=len(gold);accepted=sum(p!='abstain' for p in pred)
    errors=sum(g!=p for g,p in zip(gold,pred) if p!='abstain')
    clarification=sum(p in ('abstain','insufficient') for p in pred)
    return {'n':n,'accepted':accepted,'coverage':accepted/n,'selective_errors':errors,
        'selective_error_rate':errors/accepted if accepted else None,
        'correct_over_all':sum(g==p for g,p in zip(gold,pred))/n,
        'clarification_count':clarification,'clarification_cost_one_turn_each':clarification/n,
        'unnecessary_clarifications_under_labels':sum(p in ('abstain','insufficient') and g!='insufficient' for g,p in zip(gold,pred)),
        'assertive_coverage':sum(p in ('supported','contradicted') for p in pred)/n,
        'confusion_gold_rows':matrix}
