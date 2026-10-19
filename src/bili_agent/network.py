"""Process-wide proxy policy shared by the SDK and our aiohttp requests."""
import os
from urllib.parse import urlsplit
from urllib.request import proxy_bypass_environment

from .auth import SafeError


SDK_HOSTS = ('api.bilibili.com','api.vc.bilibili.com','api.live.bilibili.com',
             'passport.bilibili.com','www.bilibili.com','space.bilibili.com','s1.hdslb.com')


def normalize_proxy(value):
    if not isinstance(value,str):
        raise SafeError('proxy_invalid','Proxy must be an HTTP or HTTPS URL.')
    value = value.strip()
    if not value:
        return ''
    if '://' not in value:
        value = 'http://' + value
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in {'http','https'} and parsed.hostname
                 and parsed.path in {'','/'} and not parsed.query and not parsed.fragment
                 and not any(c.isspace() or ord(c)<32 or ord(c)==127 for c in value)
                 and (parsed.port is None or 1 <= parsed.port <= 65535))
    except ValueError:
        valid = False
    if not valid:
        # Never echo URLs: a proxy URL can contain a username and password.
        raise SafeError('proxy_invalid','Use an HTTP/HTTPS proxy URL or host:port. SOCKS and URL paths are unsupported.')
    return value


def selected_proxy(environ=None):
    """None means no environment override; '' explicitly selects a direct connection."""
    env = os.environ if environ is None else environ
    if 'BILI_AGENT_PROXY' in env:
        return normalize_proxy(env['BILI_AGENT_PROXY'])
    value = None
    for lower,upper in [('https_proxy','HTTPS_PROXY'),('all_proxy','ALL_PROXY'),('http_proxy','HTTP_PROXY')]:
        candidate = env.get(lower,env.get(upper))
        if candidate:
            value = candidate
            break
    if value is None:
        return None
    bypass = env.get('no_proxy',env.get('NO_PROXY',''))
    if bypass.strip() == '*':
        return ''
    if bypass and any(proxy_bypass_environment(host,{'no':bypass}) for host in SDK_HOSTS):
        raise SafeError('proxy_bypass_unsupported',
            'SDK proxy is process-wide. Set BILI_AGENT_PROXY explicitly (empty for direct) instead of per-host NO_PROXY for Bilibili/CDN.')
    return normalize_proxy(value)


def configure_sdk_proxy():
    proxy = selected_proxy()
    if proxy is None:
        return
    from bilibili_api.utils.network import request_settings
    if request_settings.get_proxy() != proxy:
        request_settings.set_proxy(proxy)
    if request_settings.get_trust_env():
        request_settings.set_trust_env(False)
    # Never modify SSL verification or the caller's environment variables.
