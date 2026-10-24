"""Auditable per-sample resource ceilings, independent of service tokenization.

Input is bounded in serialized UTF-8 bytes, NOT advertised as exact model tokens.
Requested output token capacity is reserved before dispatch and never refunded.
Actual provider usage remains separate/unknown when absent, failed or cancelled.
"""
import asyncio
import json
from dataclasses import dataclass, asdict
from time import perf_counter
from app.ccare.provider import ProviderUnavailable
from app.ccare.billing import usage_estimate

@dataclass(frozen=True)
class SampleLimits:
    max_calls: int = 5
    max_input_bytes: int = 96000
    max_output_tokens: int = 2000

    def __post_init__(self):
        if any(type(value) is not int for value in (self.max_calls, self.max_input_bytes, self.max_output_tokens)) or self.max_calls != 5 or not 1024 <= self.max_input_bytes <= 1000000 or not 500 <= self.max_output_tokens <= 2000:
            raise ValueError('Unsupported comparison envelope')

class SampleProvider:
    def __init__(self, provider, limits, *, single=False, requested_model=None):
        self.provider, self.limits, self.single, self.requested_model = provider, limits, single, requested_model
        self.calls = self.input_bytes = self.output_reserved = 0
        self.records = []

    async def complete(self, messages, **kwargs):
        input_bytes = len(json.dumps(messages, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        requested = kwargs.get('max_tokens')
        cap = self.limits.max_output_tokens if self.single else self.limits.max_output_tokens // self.limits.max_calls
        # Fail instead of silently truncating inputs or changing a condition's plan.
        if type(requested) is not int or not 1 <= requested <= cap:
            raise ProviderUnavailable('output_allocation_invalid')
        if self.calls >= self.limits.max_calls:
            raise ProviderUnavailable('sample_call_budget_exhausted')
        if self.input_bytes + input_bytes > self.limits.max_input_bytes:
            raise ProviderUnavailable('sample_input_budget_exhausted')
        if self.output_reserved + requested > self.limits.max_output_tokens:
            raise ProviderUnavailable('sample_output_budget_exhausted')
        # The global wrapper exposes calls; an exhausted global budget dispatches none.
        if getattr(self.provider, 'calls', 0) >= getattr(self.provider, 'limit', float('inf')):
            raise ProviderUnavailable('call_budget_exhausted')
        self.calls += 1
        self.input_bytes += input_bytes
        self.output_reserved += requested
        row = {'requested_model': self.requested_model, 'returned_model': None,
               'input_bytes': input_bytes, 'max_output_tokens': requested, 'usage': None,
               'elapsed_ms': None, 'failure': None, 'billing': usage_estimate(None)}
        self.records.append(row)
        tick = perf_counter()
        try:
            result = await self.provider.complete(messages, **kwargs)
            row.update(returned_model=result.model, usage=result.usage, billing=usage_estimate(result.usage))
            completion_tokens = (result.usage or {}).get('completion_tokens')
            if type(completion_tokens) is int and completion_tokens > requested:
                raise ProviderUnavailable('provider_output_budget_violation', usage=result.usage, model=result.model)
            return result
        except ProviderUnavailable as exc:
            row['failure'] = exc.code
            if exc.usage is not None:
                row.update(usage=exc.usage, returned_model=exc.model, billing=usage_estimate(exc.usage))
            raise
        except asyncio.CancelledError:
            row['failure'] = 'cancelled_or_timeout'
            raise
        finally:
            row['elapsed_ms'] = round((perf_counter() - tick) * 1000)

    def report(self):
        return {'limits': asdict(self.limits), 'model_calls': self.calls,
                'input_bytes': self.input_bytes, 'output_tokens_reserved': self.output_reserved,
                'usage_complete': bool(self.records) and all(r['usage'] is not None for r in self.records),
                'cost': None, 'calls': self.records}
