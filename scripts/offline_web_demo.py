"""Loopback-only website with real API/Engine and an explicit offline provider.

No credentials are loaded. HTTP transports are disabled before app construction.
Temporary auth storage is removed on normal shutdown; never touches budget data.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import httpx
import uvicorn
from fastapi.responses import JSONResponse
from app.ccare.api import create_app
from app.ccare.config import Settings
from app.ccare.provider import Completion


async def blocked_async(*args, **kwargs):
    raise AssertionError('Outbound HTTP forbidden in offline demo')


def blocked_sync(*args, **kwargs):
    raise AssertionError('Outbound HTTP forbidden in offline demo')


class OfflineWebProvider:
    async def complete(self, messages, **params):
        data, _ = json.JSONDecoder().raw_decode(messages[1]['content'])
        context = data.get('context', data.get('input', {}).get('context', data))
        current = context['current']
        stage = 'state' if '识别成人亲子冲突' in messages[0]['content'] else 'verify' if '独立检查候选' in messages[0]['content'] else 'generate'
        await asyncio.sleep(2 if '[MOCK:slow]' in current else 0.12)
        if stage == 'state':
            candidates = [current] + [m['content'] for m in reversed(context['history']) if m['role']=='user']
            quote = next((s for s in candidates if '难过' in s), None)
            text = json.dumps({'emotion':'sad' if quote else 'unknown', 'evidence':[quote] if quote else []},ensure_ascii=False)
        elif stage == 'verify':
            reject = '[MOCK:verdict]' in current
            text = json.dumps({'safe':not reject,'violations':['offline_fixture_rejection'] if reject else []})
        elif '[MOCK:reject]' in current:
            text = '你必须马上原谅父母。'
        else:
            text = '[离线 mock] 我先听你说，按你现在愿意的节奏继续。'
        return Completion(text, None, 'offline-mock-no-model', 200)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8767)
    args=parser.parse_args()
    httpx.AsyncHTTPTransport.handle_async_request=blocked_async
    httpx.HTTPTransport.handle_request=blocked_sync
    with tempfile.TemporaryDirectory(prefix='kinvoice-offline-web-') as tmp:
        config=Settings(_env_file=None,mode='remote',api_key='offline-fixture-never-used',
            api_base='https://offline.invalid',provider_kind='compatible',model='offline-mock-no-model',
            provider_label='离线 mock（无外发）',provider_privacy_url='https://offline.invalid',
            auth_db=Path(tmp)/'auth.db',max_tokens=400,turn_timeout=30)
        app=create_app(config,OfflineWebProvider())
        @app.middleware('http')
        async def offline_metadata(request,call_next):
            response=await call_next(request)
            if request.url.path=='/ping' and response.status_code==200:
                data=json.loads(b''.join([part async for part in response.body_iterator]))
                data['offline_mock']=True
                return JSONResponse(data,headers={k:v for k,v in response.headers.items()
                    if k not in ('content-length','content-type')})
            return response
        print('OFFLINE MOCK ONLY — no model/network calls; temporary synthetic accounts.',flush=True)
        uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning')


if __name__=='__main__': main()
