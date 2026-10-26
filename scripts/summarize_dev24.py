"""Descriptive accounting only; no clinical scores or inferred method wins."""
import argparse,json
from decimal import Decimal
from pathlib import Path

def summarize(out):
    rows=json.loads((out/'outputs.json').read_text())
    plan=json.loads((out/'plan.json').read_text())
    expected={(r['case_id'],r['arm']) for r in plan['items']}
    if len(rows)!=72 or len(expected)!=72 or {(r['case_id'],r['arm']) for r in rows}!=expected:raise ValueError('planned_denominator_mismatch')
    table=[]
    for row in rows:
        calls=[c for c in row['calls'] if c.get('wire_attempted')]
        known=[c for c in calls if isinstance(c.get('usage'),dict)]
        prompt=sum(c['usage']['prompt_tokens'] for c in known)
        completion=sum(c['usage']['completion_tokens'] for c in known)
        table.append({'case_id':row['case_id'],'arm':row['arm'],'status':row['status'],'failure':row.get('failure'),'output_present':bool(row['reply']),'calls':len(calls),'usage_known_calls':len(known),'unknown_usage_calls':len(calls)-len(known),'prompt_tokens_known':prompt,'completion_tokens_known':completion,'total_tokens_known':sum(c['usage']['total_tokens'] for c in known),'peak_estimate_cny_known':str((Decimal(prompt)*2+Decimal(completion)*8)/1000000),'elapsed_ms':row['elapsed_ms'],'question_marks_diagnostic':row['reply'].count('？')+row['reply'].count('?'),'http_statuses':[c.get('http_status') for c in calls],'models':sorted({c.get('model') for c in calls if c.get('model')})})
    numeric=['calls','usage_known_calls','unknown_usage_calls','prompt_tokens_known','completion_tokens_known','total_tokens_known','elapsed_ms']
    grouped={}
    for arm in ['strong_single','strong_multi','ccare']:
        rr=[r for r in table if r['arm']==arm]
        grouped[arm]={'planned':len(rr),'status_counts':{s:sum(r['status']==s for r in rr) for s in sorted({r['status'] for r in rr})},**{k:sum(r[k] for r in rr) for k in numeric},'peak_estimate_cny_known':str(sum((Decimal(r['peak_estimate_cny_known']) for r in rr),Decimal(0)))}
    result={'planned_cases':24,'planned_outputs':72,'candidate_outputs':0,'per_arm':grouped,'total':{k:sum(r[k] for r in table) for k in numeric},'peak_estimate_cny_known':str(sum((Decimal(r['peak_estimate_cny_known']) for r in table),Decimal(0))),'actual_bill_cny':None,'expert_scores':None,'note':'Question-mark counts are punctuation diagnostics, not necessity/quality scores. Usage-priced peak estimate is not a bill; missing usage is never zero-cost. No independent expert ratings or advantage claim.'}
    (out/'per-case-accounting.json').write_text(json.dumps(table,ensure_ascii=False,indent=2)+'\n')
    (out/'accounting.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(summarize(a.output),ensure_ascii=False))
