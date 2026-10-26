"""Aggregate real result rows and optional human ratings, without imputing failures."""
import argparse
import csv
import json
from pathlib import Path
from benchmark_ccare import summarize, METRICS

def aggregate(rows, ratings=(), key=()):
    result = summarize(rows)
    mapping = {r['blind_id']: (r['case_id'], r['condition']) for r in key}
    valid = {(r['case_id'],r['condition']) for r in rows if r['status']=='remote'}
    scores = {m:[] for m in METRICS}
    seen=set()
    for rating in ratings:
        identity = (rating['blind_id'],rating['reviewer'])
        if not rating['reviewer'] or identity in seen:
            raise ValueError('Missing reviewer or duplicate rating')
        seen.add(identity)
        if mapping.get(rating['blind_id']) not in valid:
            raise ValueError('Ratings must reference a real completed output')
        for metric in METRICS:
            if rating.get(metric,'') != '':
                value = int(rating[metric])
                if value not in (0,1,2): raise ValueError('Ratings must be 0, 1 or 2')
                scores[metric].append(value)
    result['expert_metrics']={m: {'ratings':len(v),'mean':sum(v)/len(v)} if v else 'unavailable' for m,v in scores.items()}
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('results',type=Path);p.add_argument('--ratings',type=Path);p.add_argument('--key',type=Path)
    a=p.parse_args()
    rows=[json.loads(line) for line in a.results.read_text().splitlines()]
    ratings=list(csv.DictReader(a.ratings.open())) if a.ratings else []
    key=json.loads(a.key.read_text()) if a.key else []
    print(json.dumps(aggregate(rows,ratings,key),indent=2))
