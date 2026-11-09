"""Resolve API browser handoffs without guessing public tokens from order IDs."""
import re
from urllib.parse import urlsplit

GUIDANCE = 'Finish sign-off or payment in the browser. / Completa la aprobación final o el pago en el navegador.'


def surface(value, web_url):
    parsed = urlsplit(web_url)
    origin = parsed._replace(path='', query='', fragment='').geturl()
    if 'items' in value:
        return {**value, 'items': [surface(row, origin) for row in value['items']]}
    action = value.get('browser_action')
    if action is None:
        return {**value, 'browser_guidance': GUIDANCE} if value.get('payment_url') else value
    if not isinstance(action, dict) or action.get('action') not in ('sign_off', 'pay'):
        raise ValueError('Invalid browser action. / Acción de navegador no válida.')
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid Nova origin. / Origen de Nova no válido.')
    page = 'report' if action['action'] == 'sign_off' else 'pay'
    url = action.get('url')
    if not isinstance(url, str) or not re.fullmatch(r'/body-repairs/[A-Za-z0-9_-]{1,200}/' + page, url):
        raise ValueError('Invalid browser link. / Enlace de navegador no válido.')
    return {**value, 'browser_action': {**action, 'url': origin + url}, 'browser_guidance': GUIDANCE}
