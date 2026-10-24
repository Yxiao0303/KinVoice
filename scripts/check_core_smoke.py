"""One fixed core pipeline smoke using the prior persistent authorization ledger."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.ccare.config import Settings
from app.ccare.cny_ledger import BudgetError
from app.ccare.core_smoke import existing_ledger, run_core, scenario
from app.ccare.provider import RemoteProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    if not args.live:
        print(json.dumps({'mode':'zero_call_plan', 'max_new_calls':3, 'max_tokens_per_call':400,
            'rewrites':0, 'scenario':scenario().model_dump(), 'paired_comparison':'not_run_insufficient_matched_call_budget'}, ensure_ascii=False))
        return 0
    try:
        ledger = existing_ledger()  # Never initialize an empty authorization.
        config = Settings(_env_file=None, mode='remote', api_key=os.environ.get('DEEPSEEK_API_KEY',''),
            provider_kind='deepseek', api_base='https://api.deepseek.com', model='deepseek-flash',
            provider_label='DeepSeek', provider_privacy_url='https://cdn.deepseek.com/policies/zh-CN/deepseek-privacy-policy.html',
            call_timeout=25, turn_timeout=85, max_tokens=400)
        report = asyncio.run(run_core(config, ledger, RemoteProvider(config)))
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report['result']['mode'] == 'remote' else 2
    except BudgetError as exc:
        print(json.dumps({'blocked':exc.code,'new_model_calls':0}))
    except Exception:
        print(json.dumps({'blocked':'runtime_failure','outcome':'inspect_existing_ledger_before_further_action'}))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
