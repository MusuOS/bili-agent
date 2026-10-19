import asyncio
import ssl
from .auth import SafeError


class AgentError(SafeError):
    def __init__(self, error):
        self.error = error
        super().__init__(error["code"], error.get("message", "Request failed"))


def safe_error(exc):
    if isinstance(exc, AgentError):
        return exc.error
    if isinstance(exc, SafeError):
        return {'code': exc.code, 'message': exc.message, 'retryable': False}
    code = getattr(exc, 'code', None)
    status = getattr(exc, 'status', None)
    kind = 'request_failed'
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        kind = 'timeout'
    elif isinstance(exc,ssl.SSLError) or type(exc).__name__ in {'ClientConnectorCertificateError','ClientConnectorSSLError','ClientSSLError'}:
        kind = 'tls_error'
    elif code == -101:
        kind = 'session_invalid'
    elif code in {-412, 412} or status == 412:
        kind = 'access_restricted'
    elif status == 429:
        kind = 'rate_limited'
    elif isinstance(exc, ImportError):
        kind = 'dependency_missing'
    # Never emit SDK exception text, raw responses, cookies or request URLs.
    result = {'code': kind, 'type': type(exc).__name__, 'retryable': kind == 'timeout'}
    if kind == 'tls_error':
        result['message'] = 'TLS handshake or certificate verification failed. Check the proxy protocol and trusted certificates; SSL verification was not disabled.'
    if isinstance(code, int):
        result['api_code'] = code
    if isinstance(status, int):
        result['http_status'] = status
    return result
