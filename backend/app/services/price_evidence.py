"""Use source display amounts, never guess a factor-of-100 correction."""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def amount(text):
    text = str(text or '').replace('\u00a0', ' ').strip()
    if '-' in text or re.search(r'\d\s*/\s*\d', text):
        return None
    # An amount field must contain exactly one amount, not a price range or offer.
    found = re.findall(r"\d+(?:[ .,]\d+)*|[.,]\d{1,2}", text)
    if len(found) != 1:
        return None
    if re.search(r'\d +\d{1,2}(?:\D|$)', found[0]):
        return None  # split euro/cents typography is not a decimal price
    raw = found[0].replace(' ', '')
    if ',' in raw and '.' in raw:
        decimal = ',' if raw.rfind(',') > raw.rfind('.') else '.'
        raw = raw.replace('.' if decimal == ',' else ',', '').replace(decimal, '.')
    elif ',' in raw or '.' in raw:
        sep = ',' if ',' in raw else '.'
        parts = raw.split(sep)
        if len(parts) != 2 or len(parts[1]) > 2:
            return None  # ambiguous thousands/decimal notation
        raw = '.'.join(parts)
    try:
        value = Decimal(raw)
        return value if value.is_finite() and 0 < value <= 1000000 else None
    except InvalidOperation:
        return None


def quote(summary, currency, package=False):
    cur = str(summary.get('currency') or '').upper()
    if cur not in (currency, '€' if currency == 'EUR' else currency):
        return None, 'Price currency is missing or differs from your selected currency.'
    raw = str(summary.get('price_text') or '')
    basis = summary.get('price_basis')
    if not raw or basis not in ('package', 'item', 'unit_weight', 'unknown'):
        return None, 'Displayed price text or price basis is missing; refresh this source.'
    if re.search(r'/\s*(?:kg|l(?:itre|iter)?|100\s*g)\b|per\s+(?:kg|litre|liter|kilo)', raw, re.I) or basis == 'unit_weight':
        return None, 'Only a price per kg/l is available; a full package price is required.'
    if basis == 'unknown' or (package and basis not in ('package','item')):
        return None, 'The full package/item price could not be verified.'
    if re.search(r'\b(?:cents?|centti[aä]?|pence|pennies)\b|\d\s*c\b', raw, re.I):
        return None, 'Only a minor-unit price is shown; a full displayed package price is required.'
    value = amount(raw)
    if value is None:
        return None, 'Displayed price is ambiguous or not a single current price.'
    # The display string is authoritative even when the model's numeric price
    # accidentally contains cents (249 instead of 2.49). Conversion occurs once.
    return int((value * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)), None
