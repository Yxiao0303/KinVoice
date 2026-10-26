"""Nine-call, no-retry web demonstration on the existing cumulative ledger."""
import asyncio
from dataclasses import replace
import hashlib
import json
from .cny_ledger import BudgetError
from .provider import ProviderUnavailable
from .schemas import State, Check
from .smoke import POLICY

WEB_POLICY = replace(POLICY,max_cny='50.00')
WEB_RUN = 'approved-web-demo-20261024'


class WebBudgetProvider:
    def __init__(self, ledger, provider, *, resume=False):
        if ledger.policy != WEB_POLICY:
            raise BudgetError('web_policy_mismatch')
        state=ledger.snapshot()
        previous=[a for a in state['attempts'] if a['run_id']==WEB_RUN]
        original=[a for a in state['attempts'] if a['run_id']!=WEB_RUN]
        if (state['halted'] or len(original)!=4 or sum(a['held_nano'] for a in original)!=8401408000
            or any(a['phase']!='completed' for a in state['attempts'])
            or len(previous)>9 or (previous and not resume)
            or {a['operation_id'] for a in previous}!={f'{WEB_RUN}:{n}' for n in range(1,len(previous)+1)}):
            raise BudgetError('web_demo_requires_settled_prior_history')
        self.ledger,self.provider,self.calls=ledger,provider,len(previous)
        self.records=[]
        if previous:
            with ledger.transaction() as db:ledger.event(db,WEB_RUN,'web_demo_resumed_without_reset')

    async def complete(self,messages,**params):
        if self.calls >= 9 or params.get('max_tokens') != 400:
            raise ProviderUnavailable('web_demo_call_limit')
        self.calls+=1
        operation=f'{WEB_RUN}:{self.calls}'
        fingerprint=hashlib.sha256(json.dumps({'messages':messages,'params':params,
            'model':'deepseek-flash','thinking':{'type':'disabled'}},sort_keys=True).encode()).hexdigest()
        try:
            self.ledger.reserve(operation,fingerprint,400,run_id=WEB_RUN)
            self.ledger.dispatch(operation)
        except BudgetError as exc: raise ProviderUnavailable(exc.code) from None
        record={'operation':operation,'http_status':None,'model':None,'usage':None}
        self.records.append(record)
        try:
            result=await self.provider.complete(messages,**params)
            record.update(http_status=result.http_status,model=result.model,usage=result.usage)
            if params.get('json_mode'):
                (State if '识别成人亲子冲突' in messages[0]['content'] else Check).model_validate_json(result.text)
            self.ledger.settle(operation,result.usage)
            record['status']='completed'
            return result
        except BudgetError as exc:
            record.update(status='blocked',error=exc.code)
            raise ProviderUnavailable(exc.code) from None
        except asyncio.CancelledError:
            self.ledger.mark_unknown(operation,'cancelled');record['status']='cancelled';raise
        except Exception as exc:
            usage=getattr(exc,'usage',None) or record['usage']
            self.ledger.mark_unknown(operation,'provider_failure',usage=usage)
            record.update(status='failed',error=getattr(exc,'code','invalid_response'),usage=usage)
            raise ProviderUnavailable(record['error'],usage=usage) from None
