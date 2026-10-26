"""One authorized fixed synthetic request; all dispatches retain full reservation.

Public 2026-10-24 CNY peak pricing and 1M context/max_tokens contracts are
the bound assumptions, not a provider-side account spending lock. No retries.
"""
import asyncio
from dataclasses import replace
import hashlib
import json

from .billing import usage_estimate
from .cny_ledger import BudgetError, FeePolicy
from .provider import ProviderUnavailable

OPERATION = 'authorized-single-json-20261024'
MESSAGES = [{'role': 'user', 'content': 'Synthetic connectivity test. Return only this JSON object: {"ok":true,"case":"synthetic"}'}]
PARAMS = {'temperature': 0, 'max_tokens': 400, 'json_mode': True}
POLICY = replace(FeePolicy(), provider_bound_verified=True)
FINGERPRINT = hashlib.sha256(json.dumps({
    'model': 'deepseek-flash', 'thinking': {'type': 'disabled'},
    'messages': MESSAGES, 'params': PARAMS,
}, sort_keys=True).encode()).hexdigest()


async def run_single(ledger, provider):
    if ledger.policy != POLICY:
        raise BudgetError('smoke_policy_mismatch')
    # Same fixed operation across invocations: a completed/unknown/in-flight
    # attempt can never be claimed again, even when unused money remains.
    ledger.reserve(OPERATION, FINGERPRINT, 400, run_id=OPERATION)
    ledger.dispatch(OPERATION)
    report = {'kind': 'synthetic_connectivity_only', 'requested_model': 'deepseek-flash',
              'http_status': None, 'returned_model': None, 'json_parsed': False,
              'fixed_json_matched': False, 'usage': None, 'attempted_model_calls': 1,
              'actual_billed_cny': None, 'provider_bill_cap_guaranteed': False,
              'configuration_version_verified': False}
    try:
        completion = await provider.complete(MESSAGES, **PARAMS)
        report.update(http_status=completion.http_status, returned_model=completion.model,
                      usage=completion.usage)
        try:
            value = json.loads(completion.text)
        except (ValueError, TypeError):
            raise ProviderUnavailable('invalid_json', usage=completion.usage) from None
        report['json_parsed'] = True
        if value != {'ok': True, 'case': 'synthetic'} or type(value.get('ok')) is not bool:
            raise ProviderUnavailable('unexpected_json', usage=completion.usage)
        report['fixed_json_matched'] = True
        ledger.settle(OPERATION, completion.usage)
        report.update(status='completed', usage_estimate=usage_estimate(completion.usage))
    except BudgetError as exc:
        # settle already records unknown/bound breach; preserve the full hold.
        report.update(status='blocked', error=exc.code)
    except asyncio.CancelledError:
        ledger.mark_unknown(OPERATION, 'cancelled')
        raise
    except Exception as exc:
        ledger.mark_unknown(OPERATION, 'provider_failure', usage=getattr(exc, 'usage', None))
        report.update(status='failed', error=exc.code if isinstance(exc, ProviderUnavailable) else 'provider_failure')
        if isinstance(exc, ProviderUnavailable):
            report['http_status'] = exc.http_status or report['http_status']
            report['returned_model'] = exc.model or report['returned_model']
            report['usage'] = exc.usage or report['usage']
    state = ledger.snapshot()
    report.update({k: state[k] for k in ('reserved_cny', 'remaining_reservable_cny',
        'unallocated_cny', 'known_usage_estimate_cny', 'halted')})
    return report
