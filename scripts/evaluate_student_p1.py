"""Fixed synthetic development diagnostics, not generalization or model evaluation."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.ccare.student import respond_student
from app.ccare.student_schemas import StudentRequest,StudentProfile

def run():
    path=ROOT/'research/student-p1-v1/development.jsonl'
    rows=[]
    for c in map(json.loads,path.read_text().splitlines()):
        assert c['synthetic'] and c['review_status']=='unreviewed'
        r=respond_student(StudentRequest(message=c['message'],message_id='u:1',support=c['support'],student=StudentProfile(adult_confirmed=True)))
        rows.append({'id':c['id'],'family':c['family'],'expected_action':c['expected_action'],
            'actual_action':r.strategy,'matches_developer_action':r.strategy==c['expected_action'],
            'reply':r.reply,'judgment':r.student_judgment.model_dump(),'model_calls':r.model_calls})
    return {'kind':'synthetic_unreviewed_seen_development_diagnostic','data_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'denominator':len(rows),'families':len({r['family'] for r in rows}),'action_matches':sum(r['matches_developer_action'] for r in rows),
        'paid_calls':0,'trained_models':0,'independent_ratings':None,'rows':rows}
if __name__=='__main__':print(json.dumps(run(),ensure_ascii=False,indent=2))
