"""
擎天·Oracle — DeepSeek API 封装
deepseek_chat(prompt, system=None) → str
translate(text, target_lang='zh') → str
"""
import os
import json
from openai import OpenAI

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

_client = None

def _get_client():
    global _client
    if _client is None:
        if not DEEPSEEK_API_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY not set")
        _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return _client


def deepseek_chat(prompt, system=None, temperature=0.3):
    """Call DeepSeek Chat (V3) API. Returns response text."""
    messages = []
    if system:
        messages.append({'role': 'system', 'content': system})
    messages.append({'role': 'user', 'content': prompt})
    try:
        response = _get_client().chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=4096,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise RuntimeError(f'DeepSeek API call failed: {e}')


def translate(text, target_lang='zh', source_lang='auto'):
    """Translate text for foreign trade inquiries. Preserves OE numbers."""
    lang_names = {'zh': 'Chinese', 'en': 'English', 'ru': 'Russian'}
    target_name = lang_names.get(target_lang, target_lang)
    system = (
        'You are a professional auto parts trade translator. Rules:\n'
        '1. Keep all OE numbers, part numbers, digits, units unchanged\n'
        '2. Translate part names accurately with industry terminology\n'
        '3. Output ONLY the translation, no explanations or prefixes\n'
        '4. If already in target language, return as-is'
    )
    prompt = f'Translate the following inquiry into {target_name}:\n\n{text}'
    return deepseek_chat(prompt, system=system, temperature=0.1)


def extract_inquiry(text):
    """Extract structured items from translated inquiry text."""
    system = (
        'You are an auto parts data extractor. Extract structured data from inquiry.\n'
        'Rules:\n'
        '1. Extract OE number, part name, quantity, unit for each part\n'
        '2. Default quantity=1, unit=PC\n'
        '3. Output strict JSON only, no markdown code blocks, no extra text\n'
        'Format: {"items":[{"oe_number":"xxx","name":"xxx","quantity":1,"unit":"PC"}],"customer_notes":"xxx"}'
    )
    prompt = f'Extract part info from this inquiry:\n\n{text}'
    result = deepseek_chat(prompt, system=system, temperature=0.0)
    result = result.strip()
    if result.startswith('```'):
        lines = result.split('\n')
        result = '\n'.join(lines[1:])
        if result.endswith('```'):
            result = result[:-3]
        result = result.strip()
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {'items': [], 'customer_notes': text, 'parse_error': result}


def generate_pi(inquiry_text, items, customer_name='',
                trade_term='FOB', payment_term='prepaid', currency='USD'):
    """Generate Proforma Invoice draft from quotation results."""
    lines_text = ''
    total = 0.0
    for i, item in enumerate(items, 1):
        qty = item.get('quantity', 1)
        price = item.get('unit_price', 0)
        line_total = qty * price
        total += line_total
        lines_text += (
            f'{i}. {item.get("oe_number", "N/A")} | '
            f'{item.get("name", "Part")} | '
            f'{qty} {item.get("unit", "PC")} | '
            f'{currency} {price:.2f}/pc | '
            f'{currency} {line_total:.2f}\n'
        )
    system = (
        'You are a professional trade specialist creating Proforma Invoices.\n'
        'PI format requirements:\n'
        '1. Standard international PI format, in English\n'
        '2. Include: Seller(EN TONG), Buyer, Date, PI No.(draft),\n'
        '   Description(OE+name+qty+unit price+amount), Total, Trade Term,\n'
        '   Payment Term, Estimated Delivery, Bank Info(placeholder), Validity\n'
        '3. Professional and polite tone'
    )
    prompt = (
        f'Generate a Proforma Invoice draft based on:\n\n'
        f'Customer: {customer_name or "[TBD]"}\n'
        f'Trade Term: {trade_term}\n'
        f'Payment Term: {payment_term}\n'
        f'Currency: {currency}\n\n'
        f'Line Items:\n{lines_text}\n'
        f'Total: {currency} {total:,.2f}\n\n'
        f'Original Inquiry:\n{inquiry_text[:500]}\n\n'
        f'Please generate the PI draft in English.'
    )
    return deepseek_chat(prompt, system=system, temperature=0.2)


if __name__ == '__main__':
    test_ru = 'Головка блока цилиндров ISF3.8'
    print('=' * 50)
    print('Translation test:')
    print(f'  Original: {test_ru}')
    result = translate(test_ru, 'zh')
    print(f'  Translated: {result}')
    print()
    print('=' * 50)
    print('Extraction test:')
    extracted = extract_inquiry(result)
    print(f'  Extracted: {extracted}')
