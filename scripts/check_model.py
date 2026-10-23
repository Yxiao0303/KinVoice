"""Redacted preflight by default; --live sends ONE fixed synthetic case, <=5 calls."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import uuid
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.ccare.config import Settings
from app.ccare.engine import Engine
from app.ccare.provider import RemoteProvider
from app.ccare.schemas import TurnRequest

SYNTHETIC = '虚构评审案例：我是一名20岁的大学生，父母反对我选设计专业。我很难过，现在只想有人听我说，不要给我建议。'


def preflight():
    c = Settings(mode='disabled')
    missing = [label for label,value in [('新密钥',c.api_key.strip()),('模型名',c.model),('接口地址',c.api_base),('服务商',c.provider_label),('隐私说明',c.provider_privacy_url)] if not value]
    return c, {'kind':'configuration_check_only','missing':missing,'key_present':bool(c.api_key.strip()),
               'provider':c.provider_label,'model':c.model,'api_host':urlsplit(c.api_base).hostname,
               'external_model_calls':0}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Send the built-in synthetic scenario only; up to 5 paid API calls')
    args=parser.parse_args()
    try:
        c,report=preflight()
    except Exception:
        print(json.dumps({'ready':False,'error':'invalid_local_configuration','external_model_calls':0}))
        return 2
    print(json.dumps(report,ensure_ascii=False))
    if report['missing']:
        return 2
    try:
        remote=Settings(mode='remote')
    except Exception:
        print('Remote configuration is invalid; no request was sent.')
        return 2
    if not args.live:
        print('Configuration validated. No network request made. Use --live for the synthetic connectivity check.')
        return 0
    # Freeze evidence before the first network call, retaining every outcome.
    dirty=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True,encoding='utf-8').strip()
    if dirty:
        print('Commit reviewed changes before the live check. No request was sent.')
        return 2
    run=ROOT/'experiments'/('model-check-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    run.mkdir(parents=True,exist_ok=False)
    manifest={'kind':'synthetic_connectivity_not_efficacy','commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'provider':c.provider_label,'model_requested':c.model,'provider_kind':c.provider_kind,'python':platform.python_version(),
              'max_model_calls':5,'max_output_tokens_per_call':c.max_tokens,'synthetic_message':SYNTHETIC,
              'success_criteria':['mode is remote','strategy is listen','all three processing stages completed'],
              'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'backend/app/ccare').glob('*.py')}}
    (run/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    req=TurnRequest(message=SYNTHETIC,goal='draft',eligible=True,external_consent=True)
    result=asyncio.run(Engine(remote,RemoteProvider(remote)).respond(req))
    (run/'result.json').write_text(result.model_dump_json(indent=2),encoding='utf-8')
    passed=result.mode=='remote' and result.strategy=='listen' and len(result.stages)>=3
    print(json.dumps({'passed':passed,'mode':result.mode,'strategy':result.strategy,'model_calls':result.model_calls,'failure_code':result.failure_code,'record':str(run)},ensure_ascii=False))
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
