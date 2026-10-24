"""Frozen synthetic developer exploration. Offline only; no live switch or secrets."""
import argparse
import asyncio
import csv
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.ccare.config import Settings
from benchmark_ccare import load_cases, execute, OfflineFixtureProvider, BudgetProvider
from benchmark_budget import SampleLimits, SampleProvider

PROTOCOL = ROOT/'research/exploratory-v1'
CONDITIONS = ('strong_single', 'strong_multi', 'ccare')
RATINGS = ('willingness_violation', 'unsupported_assertion', 'strategy_appropriateness',
           'safety_boundary_error', 'over_refusal', 'reviewer', 'rationale', 'unscorable_reason')

def hashes():
    paths = sorted((ROOT/'backend/app/ccare').glob('*.py')) + [
        ROOT/'scripts/benchmark_ccare.py', ROOT/'scripts/benchmark_budget.py', Path(__file__),
        ROOT/'data/development/family_stress_v1.jsonl', PROTOCOL/'protocol.md']
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

def verify_freeze():
    if json.loads((PROTOCOL/'freeze.json').read_text()) != hashes():
        raise ValueError('Frozen implementation/data/protocol changed; create a new protocol version, never tune on test outputs')

async def run(output):
    verify_freeze()
    cases = load_cases(ROOT/'data/development/family_stress_v1.jsonl')
    if any(c.split != 'dev' for c in cases):
        raise ValueError('This frozen developer protocol cannot consume sealed tests')
    output.mkdir(parents=True, exist_ok=False)
    jobs=[(c,condition) for c in cases for condition in CONDITIONS]
    random.Random(20261024).shuffle(jobs)
    rows, blind, key = [], [], []
    for index,(case,condition) in enumerate(jobs):
        sample=SampleProvider(BudgetProvider(OfflineFixtureProvider(),5), SampleLimits(),
            single=condition=='strong_single',requested_model='offline-fixture')
        config=Settings(_env_file=None,mode='disabled',api_key='',max_tokens=400).model_copy(update={'mode':'remote','model':'offline-fixture'})
        reply,status,failure='', 'failed', None
        try:
            async with asyncio.timeout(config.turn_timeout):
                reply,status,failure=await execute(case,condition,config,sample)
        except Exception as exc:
            failure=type(exc).__name__  # no raw provider message or input in logs
        blind_id=f'DEV-{index+1:03d}'  # assignment not exposed to reviewer
        rows.append({'case_id':case.case_id,'family_id':case.family_id,'condition':condition,
            'status':'mock_failed' if failure else 'mock','outcome_status':status,
            'failure_reason':failure,'budget':sample.report()})
        blind.append({'blind_id':blind_id,'input':json.dumps(case.request.model_dump(),ensure_ascii=False),
            'final_output':reply, 'material':'MOCK_ONLY_NOT_RATEABLE', **{k:'' for k in RATINGS}})
        key.append({'blind_id':blind_id,'case_id':case.case_id,'condition':condition,'failure':failure})
    (output/'rows.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    (output/'private-key.json').write_text(json.dumps(key))
    with (output/'blind-template.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(blind[0]));writer.writeheader();writer.writerows(blind)
    report={'samples':len(rows),'external_calls':0,'expert_ratings':'unavailable',
        'comparison':'not_run','all_failures_retained':True,'frozen_hashes':hashes()}
    (output/'manifest.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='frozen_hashes'}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    asyncio.run(run(parser.parse_args().output))
