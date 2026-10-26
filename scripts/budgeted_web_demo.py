"""Loopback real-model demo. Does NOT approve or migrate the existing budget."""
import json
import argparse
import os
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import uvicorn
from app.ccare.api import create_app
from app.ccare.config import Settings
from app.ccare.cny_ledger import CNYLedger,DEFAULT_LEDGER,BudgetError
from app.ccare.engine import Engine
from app.ccare.provider import RemoteProvider
from app.ccare.web_budget import WEB_POLICY,WebBudgetProvider


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume-within-cap',action='store_true')
    args=parser.parse_args()
    if not DEFAULT_LEDGER.is_file(): raise BudgetError('existing_ledger_required')
    ledger=CNYLedger(DEFAULT_LEDGER,WEB_POLICY)
    with tempfile.TemporaryDirectory(prefix='kinvoice-real-demo-') as tmp:
        config=Settings(_env_file=None,mode='remote',api_key=os.environ.get('DEEPSEEK_API_KEY',''),
            api_base='https://api.deepseek.com',provider_kind='deepseek',model='deepseek-flash',
            provider_label='DeepSeek',provider_privacy_url='https://cdn.deepseek.com/policies/zh-CN/deepseek-privacy-policy.html',
            auth_db=Path(tmp)/'auth.db',max_tokens=400,call_timeout=25,turn_timeout=85)
        provider=WebBudgetProvider(ledger,RemoteProvider(config),resume=args.resume_within_cap)
        app=create_app(config,provider)
        app.state.engine.generation_attempts=1
        try: uvicorn.run(app,host='127.0.0.1',port=8768,log_level='warning')
        finally:
            # Numeric/sanitized audit only. No prompts, responses, tokens or keys.
            (DEFAULT_LEDGER.parent/'web_demo_result.json').write_text(json.dumps({
                'calls':provider.records,'ledger':ledger.snapshot()},ensure_ascii=False,indent=2))


if __name__=='__main__': main()
