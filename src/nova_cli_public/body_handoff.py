"""Resolve API browser handoffs without guessing public tokens from order IDs."""
import re
from urllib.parse import urlsplit

GUIDANCE = 'Finish sign-off or payment in the browser. / Completa la aprobación final o el pago en el navegador.'
UNAVAILABLE = 'Link not available. / Enlace no disponible.'
PAYMENT_LABEL = 'Invoice or receipt / Factura o recibo'


def valid_url(value, schemes):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port
        return bool(parsed.scheme in schemes and parsed.hostname and not parsed.username
            and not parsed.password and "\\" not in value)
    except ValueError:
        return False


def surface(value, web_url):
    if 'items' in value:
        return {**value, 'items': [surface(row, web_url) for row in value['items']]}
    result = dict(value)
    notes = []
    payment_url = value.get('payment_url')
    if payment_url is not None:
        if valid_url(payment_url, ('https',)):
            result['payment_link_label'] = PAYMENT_LABEL
        else:
            result['payment_url'] = None
            notes.append(UNAVAILABLE)
    action = value.get('browser_action')
    if action is not None:
        kind = action.get('action') if isinstance(action, dict) else None
        page = 'report' if kind == 'sign_off' else 'pay' if kind == 'pay' else None
        url = action.get('url') if isinstance(action, dict) else None
        if (page and isinstance(url, str)
                and re.fullmatch(r'/body-repairs/[A-Za-z0-9_-]{1,200}/' + page, url)
                and valid_url(web_url, ('http', 'https'))):
            origin = urlsplit(web_url)._replace(path='', query='', fragment='').geturl()
            result['browser_action'] = {**action, 'url': origin + url}
            notes.insert(0, GUIDANCE)
        else:
            result['browser_action'] = None
            if UNAVAILABLE not in notes:
                notes.append(UNAVAILABLE)
    if notes:
        result['browser_guidance'] = ' '.join(notes)
    return result
