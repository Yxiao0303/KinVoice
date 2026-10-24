"""Zero-call fee plan or durable offline ledger simulation. No live transport."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.ccare.cny_ledger import BudgetError, CNYLedger, FeePolicy, OfflineMonetaryProvider, yuan
from app.ccare.billing import live_readiness
from app.ccare.provider import Completion, ProviderUnavailable

class Fixture:
    offline_budget_fixture = True
    def __init__(self): self.calls = 0
    async def complete(self, *args, **kwargs):
        self.calls += 1
        return Completion('{}', {'prompt_tokens':10,'completion_tokens':2,'total_tokens':12,
            'completion_tokens_details':{'reasoning_tokens':1}}, 'offline-fixture')

async def simulate(args):
    policy=FeePolicy()
    ledger=CNYLedger(args.ledger,policy,clock=lambda:policy.verified_at+3600)
    fixture=Fixture()
    provider=OfflineMonetaryProvider(ledger,fixture)
    outcomes=[]
    for _ in range(args.attempts):
        try:
            await provider.complete([{'role':'user','content':'Return JSON for this fictional fixture.'}],temperature=0,max_tokens=400,json_mode=True)
            outcomes.append('mock_completed')
        except ProviderUnavailable as exc: outcomes.append(exc.code)
    state=ledger.snapshot()
    print(json.dumps({'kind':'offline_fee_reservation_not_real_cost','clock_kind':'frozen_offline_snapshot','fixture_calls':fixture.calls,
        'external_model_calls':0,'outcomes':outcomes,'reserved_cny':state['reserved_cny'],
        'remaining_reservable_cny':state['remaining_reservable_cny'],
        'mock_usage_estimate_cny':state['known_usage_estimate_cny'],
        'actual_billed_cny':None,'provider_bill_cap_guaranteed':False,'halted':state['halted']}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--mock',action='store_true')
    mode.add_argument('--live',action='store_true')
    parser.add_argument('--ledger',type=Path)
    parser.add_argument('--attempts',type=int,default=6)
    args=parser.parse_args()
    if args.live:
        print(json.dumps(live_readiness()))
        return 2
    if args.mock:
        if args.ledger is None or not 1 <= args.attempts <= 20: parser.error('--mock requires an explicit offline --ledger path and 1..20 attempts')
        try: asyncio.run(simulate(args))
        except BudgetError as exc:
            print(json.dumps({'blocked':exc.code,'external_model_calls':0}))
            return 2
        return 0
    policy=FeePolicy()
    print(json.dumps({'kind':'offline_plan_only','policy':json.loads(policy.serialized()),
        'worst_reservation_per_400_token_attempt_cny':yuan(policy.amount(policy.max_prompt_tokens,400)),
        'external_model_calls':0,'provider_bill_cap_guaranteed':False,'live_enabled':False}))
    return 0

if __name__=='__main__': raise SystemExit(main())
