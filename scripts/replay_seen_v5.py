"""Offline seen-output replay: flags are diagnostics, never revised v5 scores."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from audit_frozen_research import audit
from app.ccare.schemas import TurnRequest
from app.ccare.engine import local_state
from app.ccare.emotion_grounding import unsupported_emotion
from three_arm import ActionSelector

def replay():
    audit('batch-evaluation-v5')
    path=ROOT/'research/batch-evaluation-v5/results/outputs.json'
    rows=json.loads(path.read_text())
    cases={r['case_id']:r for r in map(json.loads,(ROOT/'research/evaluation-pack-v1/development.jsonl').read_text().splitlines())}
    results=[]
    for row in rows:
        req=TurnRequest(**cases[row['case_id']]['context'])
        decision=ActionSelector().select(req,local_state(req),[])
        results.append({'case_id':row['case_id'],'arm':row['arm'],
            'original_status':row['status'],'original_reply':row['reply'],
            'original_decision':row.get('decision'),
            'current_local_selection_without_new_extraction':decision.selected,
            'seen_reply_emotion_flags':unsupported_emotion(row['reply'],req)})
    return {'kind':'seen_development_replay_not_new_model_results','paid_calls':0,
        'original_outputs_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'denominator':len(results),'rows':results}
if __name__=='__main__':
    print(json.dumps(replay(),ensure_ascii=False,indent=2))
