"""Zero-call preflight or one fixed synthetic JSON request with durable CNY reserve."""
import argparse
import json
from pathlib import Path
import sys
import asyncio
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.ccare.config import Settings
from app.ccare.cny_ledger import CNYLedger, DEFAULT_LEDGER, BudgetError
from app.ccare.provider import RemoteProvider
from app.ccare.smoke import POLICY, run_single

SYNTHETIC = '虚构评审案例：我是一名20岁的大学生，父母反对我选设计专业。我很难过，现在只想有人听我说，不要给我建议。'


def preflight():
    c = Settings(mode='disabled')
    present = {'KINVOICE_API_KEY_or_DEEPSEEK_API_KEY': bool(c.api_key.strip()), 'KINVOICE_MODEL': bool(c.model),
               'KINVOICE_API_BASE': bool(c.api_base), 'KINVOICE_PROVIDER_KIND': c.provider_kind == 'deepseek',
               'KINVOICE_PROVIDER_LABEL': bool(c.provider_label), 'KINVOICE_PROVIDER_PRIVACY_URL': bool(c.provider_privacy_url)}
    missing = [name for name, value in present.items() if not value]
    return c, {'kind':'configuration_check_only', 'credential_scope':'process/env-file settings only; proxy credential injection is not probed', 'variables_present':present,
               'missing':missing, 'key_present':present['KINVOICE_API_KEY_or_DEEPSEEK_API_KEY'], 'external_model_calls':0}


def main():
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='One authorized fixed JSON request; canonical persistent ledger, no retries')
    args=parser.parse_args()
    if args.live:
        try:
            # Fixed endpoint/model; use the existing platform binding only.
            # No env-file credentials or fallback keys for this authorized test.
            c = Settings(_env_file=None, mode='remote', api_key=os.environ.get('DEEPSEEK_API_KEY', ''),
                provider_kind='deepseek', api_base='https://api.deepseek.com', model='deepseek-flash',
                provider_label='DeepSeek', provider_privacy_url='https://cdn.deepseek.com/policies/zh-CN/deepseek-privacy-policy.html',
                call_timeout=30, max_tokens=400)
            ledger = CNYLedger(DEFAULT_LEDGER, POLICY)
            report = asyncio.run(run_single(ledger, RemoteProvider(c)))
            print(json.dumps(report))
            return 0 if report['status'] == 'completed' else 2
        except BudgetError as exc:
            print(json.dumps({'blocked': exc.code, 'new_model_calls': 0}))
        except Exception:
            # Do not reveal settings, headers, raw exceptions or response bodies.
            print(json.dumps({'blocked': 'configuration_or_runtime_failure', 'outcome': 'inspect_canonical_ledger_before_any_further_action'}))
        return 2
    try:
        _, report=preflight()
        print(json.dumps(report,ensure_ascii=False))
        if report['missing']: return 2
        Settings(mode='remote')  # Configuration validation only; never opens a client.
    except Exception:
        print(json.dumps({'ready':False,'error':'invalid_local_configuration','external_model_calls':0}))
        return 2
    print('Configuration validated with zero calls. --live permits only one fixed JSON attempt with durable CNY reservation.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
