"""Tiny fitted character-bigram naive Bayes; synthetic current-listen claim only.
No deep model, calibrated confidence, clinical labels or online policy authority.
"""
from collections import Counter
import math

LABELS = ('supported', 'contradicted', 'insufficient')


def features(text):
    text = ''.join(text.split())
    return Counter(text[i:i+2] for i in range(len(text)-1))


def fit(rows, alpha=1.0):
    if not rows or alpha != 1.0:
        raise ValueError('Frozen training requires nonempty rows and alpha=1')
    counts={label:Counter() for label in LABELS};documents=Counter()
    for row in rows:
        if row['split'] != 'train' or row['label'] not in LABELS:
            raise ValueError('Only labelled train rows may be fitted')
        counts[row['label']].update(features(row['text']))
        documents[row['label']] += 1
    vocabulary=sorted(set().union(*(set(v) for v in counts.values())))
    return {'version':'char2-mnb-v1','alpha':alpha,'labels':list(LABELS),
            'documents':dict(documents),'vocabulary':vocabulary,
            'counts':{k:dict(sorted(v.items())) for k,v in counts.items()}}


def predict(model, text):
    vocab=set(model['vocabulary']);observed=features(text);alpha=model['alpha']
    scores={}
    for label in LABELS:
        counts=model['counts'][label]
        score=math.log((model['documents'].get(label,0)+alpha)/(sum(model['documents'].values())+alpha*len(LABELS)))
        denominator=sum(counts.values())+alpha*len(vocab)
        for feature,n in observed.items():
            if feature in vocab:
                score += n*math.log((counts.get(feature,0)+alpha)/denominator)
        scores[label]=score
    return max(LABELS,key=lambda label:scores[label])  # fixed tie order; no probability claim


class LearnedListenAdapter:
    def __init__(self, model): self.model=model
    def assess(self, req, claim):
        from .research import provenance, EvidenceVerdict, source_for
        issue=provenance(req,claim)
        if issue: return issue
        if claim.field != 'support_intent' or claim.value != 'listen':
            return EvidenceVerdict(verdict='insufficient',reason='ambiguous')
        return EvidenceVerdict(verdict=predict(self.model,source_for(req,claim)[1]),
            reason='ambiguous',quote=claim.quote)
