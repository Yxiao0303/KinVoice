"""Offline accounting helpers. USD estimates are not an enforced CNY ceiling."""
from decimal import Decimal
import os

PRICE_SOURCE = 'https://api-docs.deepseek.com/quick_start/pricing/'
PRICE_VERSION = 'deepseek-flash-2026-10-24-peak-usd'
# Public snapshot; peak prices, per million tokens. No fabricated FX conversion.
RATES = {'cache_hit': Decimal('0.006'), 'cache_miss': Decimal('0.3'), 'output': Decimal('1.2')}
CNY_RATES = {'cache_hit': Decimal('0.04'), 'cache_miss': Decimal('2'), 'output': Decimal('8')}
CNY_PRICE_SOURCE = 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/'


def usage_estimate(usage):
    """Completion already contains reasoning tokens: never charge them twice."""
    unknown = {'estimated_usd': None, 'estimated_cny': None, 'actual_cny': None, 'price_version': PRICE_VERSION,
               'cny_cap_enforced': False}
    if not isinstance(usage, dict): return unknown
    keys = ('prompt_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens', 'completion_tokens', 'total_tokens')
    if not all(type(usage.get(k)) is int and usage[k] >= 0 for k in keys): return unknown
    prompt, hit, miss, output, total = (usage[k] for k in keys)
    if hit + miss != prompt or total != prompt + output: return unknown
    details = usage.get('completion_tokens_details', {})
    if not isinstance(details, dict): return unknown
    reasoning = details.get('reasoning_tokens')
    if reasoning is not None and (type(reasoning) is not int or not 0 <= reasoning <= output): return unknown
    estimate = (hit*RATES['cache_hit'] + miss*RATES['cache_miss'] + output*RATES['output']) / Decimal(1000000)
    cny = (hit*CNY_RATES['cache_hit'] + miss*CNY_RATES['cache_miss'] + output*CNY_RATES['output']) / Decimal(1000000)
    return {**unknown, 'estimated_usd': str(estimate), 'estimated_cny': str(cny)}


def live_readiness():
    # Explicitly fail closed. Token/call ceilings and post-hoc USD accounting do
    # not establish a verified pre-dispatch total billable token bound or CNY reserve.
    present = {name: bool(os.environ.get(name)) for name in ('DEEPSEEK_API_KEY', 'KINVOICE_API_KEY')}
    blocked = ['runtime_secret_readiness_unverified', 'destination_access_not_verified', 'provider_billing_bounds_not_verified']
    return {'live_enabled': False, 'process_variables_present': present,
            'credential_observation': 'Process presence is not proxy-injection readiness; consult current runtime metadata.',
            'offline_reservation_ledger_implemented': True, 'provider_bill_cap_guaranteed': False, 'authorized_cny_cap': '10.00', 'external_model_calls': 0,
            'blocked': blocked,
            'cny_cap_enforced': False, 'price_version': PRICE_VERSION}
