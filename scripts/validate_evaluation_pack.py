"""Offline artifact checks only. Never import inference code or score responses."""
import ast
import csv
import hashlib
import io
import json
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'research/evaluation-pack-v1'
BASE = '2c04bb07cc372273979cf8238c4e719592d6992d'
ACTIONS = {'L','D','A','C','S','D_conditional','A_cautious'}
QUESTIONS = {'not_required','required','required_or_conditional','required_or_direct_safety'}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def rows():
    return [json.loads(line) for split in ('development','candidate_holdout')
            for line in (PACK / f'{split}.jsonl').read_text().splitlines()]

def norm(text):
    return ''.join(re.findall(r'[\u4e00-\u9fffA-Za-z]',text)).lower()

def grams(text):
    return {text[i:i+3] for i in range(max(0,len(text)-2))}

def similarity(a,b):
    a,b=norm(a),norm(b)
    ga,gb=grams(a),grams(b)
    j=len(ga & gb)/max(1,len(ga | gb))
    ratio=SequenceMatcher(None,a,b,autojunk=False).ratio()
    return {'sequence_ratio':round(ratio,6),'trigram_jaccard':round(j,6),'exact':a==b}

def flagged(s):
    return s['exact'] or s['sequence_ratio']>=.72 or s['trigram_jaccard']>=.40

def old_corpus():
    paths=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
    paths=[p for p in paths if (p.startswith(('research/','data/development/','docs/verification/')) and p.endswith(('.json','.jsonl'))) or (p.startswith('backend/tests/') and p.endswith('.py'))]
    corpus=[];hashes={}
    def walk(value,path):
        if isinstance(value,dict):
            for k,v in value.items():
                if k in {'message','text','content','current_message','utterance'} and isinstance(v,str) and len(norm(v))>=12:
                    corpus.append((path,v))
                else:walk(v,path)
        elif isinstance(value,list):
            for v in value:walk(v,path)
    for p in paths:
        raw=subprocess.check_output(['git','show',f'{BASE}:{p}'],cwd=ROOT);hashes[p]=sha(raw)
        text=raw.decode()
        if p.endswith('.py'):
            for node in ast.walk(ast.parse(text)):
                if isinstance(node,ast.Constant) and isinstance(node.value,str) and len(norm(node.value))>=12 and re.search('[\u4e00-\u9fff]',node.value):corpus.append((p,node.value))
        elif p.endswith('.jsonl'):
            for line in text.splitlines():
                if line.strip():walk(json.loads(line),p)
        else:walk(json.loads(text),p)
    return sorted(set(corpus)),hashes

def duplicate_audit(data):
    old,hashes=old_corpus();cross=[];within=[];nearest=[];old_flags=[]
    for i,a in enumerate(data):
        for b in data[i+1:]:
            s=similarity(a['context']['message'],b['context']['message'])
            item={'left':a['case_id'],'right':b['case_id'],**s}
            (cross if a['split']!=b['split'] else within).append(item)
        scores=[]
        for path,text in old:
            s=similarity(a['context']['message'],text)
            item={'case_id':a['case_id'],'old_path':path,'old_text_sha256':sha(text.encode()),**s}
            scores.append(item)
            if flagged(s):old_flags.append(item)
        nearest.append(max(scores,key=lambda x:x['sequence_ratio']))
    return {'base_commit':BASE,'scope':'current-message lexical comparison against original JSON utterance fields and Chinese test literals; no algorithm/model execution','thresholds':{'sequence_ratio':.72,'trigram_jaccard':.40},'old_source_hashes':hashes,'old_unique_texts':len(old),'cross_split_pairs':len(cross),'cross_split_flags':[x for x in cross if flagged(x)],'same_split_flags':[x for x in within if flagged(x)],'old_flags':old_flags,'top_cross_split':sorted(cross,key=lambda x:x['sequence_ratio'],reverse=True)[:12],'nearest_old_per_case':nearest,'limitations':'Lexical only; not proof of semantic independence. Same author; mechanisms overlap. Full context and family definitions also need human review.'}

def validate_rows(data):
    assert len(data)==60
    assert len({r['case_id'] for r in data})==60
    families={};templates={}
    for split,n,f in [('development',24,12),('candidate_holdout',36,18)]:
        selected=[r for r in data if r['split']==split]
        assert len(selected)==n
        families[split]={r['family_id'] for r in selected}
        templates[split]={r['template_family_id'] for r in selected}
        assert len(families[split])==f and len(templates[split])==f
        assert all(sum(r['family_id']==fam for r in selected)==2 for fam in families[split])
    assert not families['development'] & families['candidate_holdout']
    assert not templates['development'] & templates['candidate_holdout']
    for r in data:
        assert r['synthetic'] is True and r['review_status']=='unreviewed'
        assert r['professional_review_required'] is True and r['reference_answer'] is None
        for k in ['target_behaviors','prohibited_behaviors','label_uncertainty','professional_review_focus','coverage']:assert r[k]
        assert set(r['acceptable_actions'])<=ACTIONS and r['acceptable_actions']
        assert r['clarification_requirement'] in QUESTIONS
        msg=r['context']['message']
        for turn in r['context']['history']:assert turn['role'] in {'user','assistant'} and turn['content']
        assert r['key_evidence']
        for e in r['key_evidence']:
            assert e['source']=='current' and 0<=e['start']<e['end']<=len(msg)
            assert msg[e['start']:e['end']]==e['quote']
    assert len({norm(r['context']['message']) for r in data})==60

def validate():
    manifest=json.loads((PACK/'freeze.json').read_text())
    actual={str(p.relative_to(PACK)) for p in PACK.rglob('*') if p.is_file() and p.name!='freeze.json'}
    assert actual==set(manifest['sha256']), 'Frozen file set changed'
    for p,digest in manifest['sha256'].items():assert sha((PACK/p).read_bytes())==digest,p
    assert manifest['base_commit']==BASE
    assert manifest['validator_sha256']==sha(Path(__file__).read_bytes())
    data=rows();validate_rows(data)
    index=list(csv.DictReader(io.StringIO((PACK/'case-index.csv').read_text())))
    assert len(index)==60
    for r,i in zip(data,index):
        for k in ['case_id','split','family_id','template_family_id','review_status']:assert r[k]==i[k]
        assert ';'.join(r['coverage'])==i['coverage']
    review=list(csv.DictReader(io.StringIO((PACK/'blind-review-blank.csv').read_text())))
    assert len(review)==180
    for row in review:
        assert row['rating_status']=='not_rated'
        assert all(v=='' for k,v in row.items() if k not in {'case_id','rating_status'})
    assert all(sum(x['case_id']==r['case_id'] for x in review)==3 for r in data)
    assert not list(csv.DictReader(io.StringIO((PACK/'blind-key-blank.csv').read_text())))
    audit=duplicate_audit(data)
    assert audit==json.loads((PACK/'duplicate-audit.json').read_text()),'Duplicate audit changed'
    assert not audit['cross_split_flags'] and not audit['old_flags'],'Review duplicate flags before publishing a new version'
    return {'cases':60,'development':24,'candidate_holdout':36,'families':30,'multi_turn':sum(bool(r['context']['history']) for r in data),'blank_review_rows':180,'old_unique_texts':audit['old_unique_texts'],'external_calls':0,'algorithm_predictions':0,'ratings':0,'frozen_hashes_verified':True}

if __name__=='__main__':print(json.dumps(validate(),ensure_ascii=False))
