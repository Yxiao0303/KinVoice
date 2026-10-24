"""Redacted zero-call preflight. Live remains blocked until verified CNY readiness."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.ccare.config import Settings
from app.ccare.billing import live_readiness

SYNTHETIC = '虚构评审案例：我是一名20岁的大学生，父母反对我选设计专业。我很难过，现在只想有人听我说，不要给我建议。'


def preflight():
    c = Settings(mode='disabled')
    present = {'KINVOICE_API_KEY_or_DEEPSEEK_API_KEY': bool(c.api_key.strip()), 'KINVOICE_MODEL': bool(c.model),
               'KINVOICE_API_BASE': bool(c.api_base), 'KINVOICE_PROVIDER_KIND': c.provider_kind == 'deepseek',
               'KINVOICE_PROVIDER_LABEL': bool(c.provider_label), 'KINVOICE_PROVIDER_PRIVACY_URL': bool(c.provider_privacy_url)}
    missing = [name for name, value in present.items() if not value]
    return c, {'kind':'configuration_check_only', 'variables_present':present,
               'missing':missing, 'key_present':present['KINVOICE_API_KEY_or_DEEPSEEK_API_KEY'], 'external_model_calls':0}


def main():
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Blocked until secure configuration and verified CNY budget readiness')
    args=parser.parse_args()
    if args.live:
        print(json.dumps(live_readiness()))
        return 2
    try:
        _, report=preflight()
        print(json.dumps(report,ensure_ascii=False))
        if report['missing']: return 2
        Settings(mode='remote')  # Configuration validation only; never opens a client.
    except Exception:
        print(json.dumps({'ready':False,'error':'invalid_local_configuration','external_model_calls':0}))
        return 2
    print('Configuration validated with zero calls. Live remains blocked pending verified CNY readiness.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
