"""Fixed synthetic core smoke; three new calls at most, on the existing ledger."""
import asyncio
import hashlib
import json

from .billing import usage_estimate
from .cny_ledger import BudgetError, CNYLedger, DEFAULT_LEDGER
from .engine import Engine
from .provider import ProviderUnavailable
from .reviews import digest
from .schemas import TurnRequest, State, Check
from .smoke import POLICY, OPERATION

RUN = 'authorized-core-smoke-20261024'
TEXT = '虚构案例：我是一名20岁的大学生。父母希望我周末回家，我想留校准备课程展示。这让我有些难过。'


def scenario():
    base = dict(source_message_id='synthetic-core-current', source_digest=digest(TEXT), source_text=TEXT)
    return TurnRequest(message_id='synthetic-core-current', message=TEXT, goal='draft',
        eligible=True, external_consent=True, reviews=[
            dict(**base, field='support_intent', value='listen', action='correct', revision=1),
            dict(**base, field='emotion', value='sad', action='revoke', revision=1)])


def existing_ledger(path=DEFAULT_LEDGER):
    if not path.exists():
        raise BudgetError('existing_authorization_ledger_required')
    ledger = CNYLedger(path, POLICY)
    verify_initial(ledger)
    return ledger


def verify_initial(ledger):
    if ledger.policy != POLICY:
        raise BudgetError('core_smoke_policy_mismatch')
    ledger.policy.validate(ledger.clock())
    state = ledger.snapshot()
    if (state['halted'] or len(state['attempts']) != 1
        or state['attempts'][0]['operation_id'] != OPERATION
        or state['attempts'][0]['phase'] != 'completed'
        or state['reserved_cny'] != '2.100352'):
        raise BudgetError('core_smoke_requires_completed_single_and_no_prior_core_attempt')


class CoreBudgetProvider:
    def __init__(self, ledger, provider):
        verify_initial(ledger)
        self.ledger, self.provider = ledger, provider
        self.records = []
        self.propagation = None
        self.extracted = None

    async def complete(self, messages, **params):
        index = len(self.records)
        if index >= 3:
            raise ProviderUnavailable('core_call_limit')
        stage = ('state', 'generate', 'verify')[index]
        if params.get('max_tokens') != 400 or params.get('json_mode') != (stage != 'generate'):
            raise ProviderUnavailable('core_stage_parameters_rejected')
        if stage == 'generate':
            payload = json.loads(messages[1]['content'])
            self.propagation = {
                'emotion_revoked': payload['state']['emotion'] == 'unknown',
                'intent_corrected': payload['state']['support_intent'] == 'listen',
                'strategy_listen': payload['strategy'] == 'listen',
            }
            if not all(self.propagation.values()):
                raise ProviderUnavailable('core_review_propagation_failed')
        operation = f'{RUN}:{stage}'
        fingerprint = hashlib.sha256(json.dumps({'messages': messages, 'params': params,
            'model': 'deepseek-flash', 'thinking': {'type': 'disabled'}}, sort_keys=True).encode()).hexdigest()
        try:
            self.ledger.reserve(operation, fingerprint, 400, run_id=RUN)
            self.ledger.dispatch(operation)
        except BudgetError as exc:
            raise ProviderUnavailable(exc.code) from None
        record = {'stage': stage, 'http_status': None, 'returned_model': None, 'usage': None}
        self.records.append(record)
        try:
            result = await self.provider.complete(messages, **params)
            record.update(http_status=result.http_status, returned_model=result.model, usage=result.usage)
            # Validate structured output before settlement or any later request.
            if stage == 'state':
                self.extracted = State.model_validate_json(result.text).model_dump()
            if stage == 'verify':
                Check.model_validate_json(result.text)
            self.ledger.settle(operation, result.usage)
            record.update(status='completed', estimate=usage_estimate(result.usage))
            return result
        except BudgetError as exc:
            record.update(status='blocked', error=exc.code)
            raise ProviderUnavailable(exc.code) from None
        except asyncio.CancelledError:
            self.ledger.mark_unknown(operation, 'cancelled')
            record.update(status='cancelled')
            raise
        except Exception as exc:
            usage = getattr(exc, 'usage', None) or record['usage']
            self.ledger.mark_unknown(operation, 'provider_failure', usage=usage)
            code = exc.code if isinstance(exc, ProviderUnavailable) else 'invalid_core_response'
            record.update(status='failed', error=code, usage=usage,
                http_status=getattr(exc, 'http_status', None) or record['http_status'])
            raise ProviderUnavailable(code, usage=usage, model=record['returned_model']) from None


async def run_core(config, ledger, provider):
    wrapped = CoreBudgetProvider(ledger, provider)
    result = await Engine(config, wrapped, generation_attempts=1).respond(scenario())
    state = ledger.snapshot()
    # Only this fixed synthetic scenario can enter this entry point. No arbitrary
    # user text CLI option, no website path, no rewrites or automatic retries.
    return {'kind':'synthetic_core_functional_smoke_not_efficacy',
        'calls':wrapped.records, 'raw_extracted_state':wrapped.extracted,
        'generation_review_propagation':wrapped.propagation,
        'result':result.model_dump(),
        'cumulative':{k:state[k] for k in ('authorization','reserved_cny',
            'remaining_reservable_cny','unallocated_cny','known_usage_estimate_cny','halted')},
        'total_dispatched_attempts':len(state['attempts']),
        'actual_billed_cny':None, 'paired_comparison_executed':False}
