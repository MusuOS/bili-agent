"""Pure HTTP QR login; never expose QR keys or returned cookies in events."""
import asyncio
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .auth import SafeError
from .collect import save_private
from .network import selected_proxy


class HttpBackend:
    def __init__(self, session, proxy=None):
        self.session = session
        self.proxy = proxy

    async def request(self, url, **kwargs):
        async with self.session.get(url, allow_redirects=False, proxy=self.proxy, **kwargs) as response:
            response.raise_for_status()
            result = await response.json()
            cookies = {name: morsel.value for name, morsel in response.cookies.items()}
        if result.get('code') != 0 or not isinstance(result.get('data'), dict):
            raise SafeError('login_api_failed', 'Login API did not return a successful response.')
        data = result['data']
        if cookies:
            data['_response_cookies'] = cookies
        return data

    async def generate(self):
        return await self.request('https://passport.bilibili.com/x/passport-login/web/qrcode/generate',
                                  params={'source': 'main-fe-header'})

    async def poll(self, key):
        return await self.request('https://passport.bilibili.com/x/passport-login/web/qrcode/poll',
                                  params={'qrcode_key': key, 'source': 'main-fe-header'})

    async def validate(self, credential):
        async with self.session.get('https://api.bilibili.com/x/web-interface/nav', proxy=self.proxy,
                cookies={'SESSDATA': credential['sessdata'], 'bili_jct': credential['bili_jct'],
                         'DedeUserID': credential['dedeuserid']}, allow_redirects=False) as response:
            response.raise_for_status()
            result = await response.json()
        data = result.get('data') or {}
        if result.get('code') != 0 or data.get('isLogin') is not True or str(data.get('mid')) != credential['dedeuserid']:
            raise SafeError('login_validation_failed', 'New session could not be validated; existing session was preserved.')


def login_target(value=None):
    return Path(value or os.environ.get('BILI_AGENT_CREDENTIAL_FILE') or
                '~/.config/bili-agent/credential.json').expanduser()


def parse_credential(data):
    link = urlparse(data.get('url', ''))
    # Callback URL is never fetched. Modern responses can carry credentials in Set-Cookie.
    fields = {key.lower(): values[0] for key, values in parse_qs(link.query).items()}
    cookies = {key.lower(): value for key, value in data.get('_response_cookies', {}).items()}
    result = {key: cookies.get(source) or fields.get(source, '') for key, source in
              [('sessdata', 'sessdata'), ('bili_jct', 'bili_jct'), ('dedeuserid', 'dedeuserid')]}
    if not all(isinstance(value, str) and value for value in result.values()) or not result['dedeuserid'].isdigit():
        raise SafeError('login_response_invalid', 'Incomplete login response; no credentials saved.')
    refresh = data.get('refresh_token')
    if isinstance(refresh, str) and refresh:
        result['ac_time_value'] = refresh
    return result


def render_qr(url, path):
    import qrcode
    path.parent.mkdir(parents=True, exist_ok=True)
    # mkstemp keeps the QR private from its first write, even for explicit paths.
    fd, temporary = tempfile.mkstemp(prefix='.qr-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            qrcode.make(url).save(out, format='PNG')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


async def login(args, backend=None, sink=None, render=render_qr):
    target = login_target(args.credential_file)
    if target.exists() and not args.replace:
        raise SafeError('credential_exists', 'Session file already exists. Use --replace to intentionally replace it.')
    directory = Path(tempfile.mkdtemp(prefix='bili-agent-login-')) if not args.qr_file else None
    qr = args.qr_file or directory / 'qrcode.png'
    if qr.exists():
        if directory:
            directory.rmdir()
        raise SafeError('qr_file_exists', 'QR output already exists; choose a new path.')
    if qr.resolve() == target.resolve() or (args.output and args.output.resolve() in {target.resolve(), qr.resolve()}):
        if directory:
            directory.rmdir()
        raise SafeError('unsafe_output', 'QR, event output and credential files must have distinct paths.')
    def emit(event, data=None, ok=True):
        value = {'schema_version': 1, 'ok': ok, 'command': 'login', 'route': 'pure-http',
                 'event': event, 'data': data or {}}
        if sink:
            sink(value)
        else:
            text = json.dumps(value, ensure_ascii=False)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, 'w') as out:
                    os.fchmod(out.fileno(), 0o600)
                    out.write(text + '\n')
            print(text, flush=True)
    async def run(active):
        data = await active.generate()
        url = data.get('url', '')
        parsed = urlparse(url)
        if not data.get('qrcode_key') or parsed.scheme != 'https' or parsed.hostname not in {'passport.bilibili.com', 'account.bilibili.com'}:
            raise SafeError('login_response_invalid', 'Unexpected QR response.')
        render(url, qr)
        emit('qrcode', {'qr_file': str(qr.resolve()), 'wait_timeout_seconds': args.timeout,
                        'instruction': 'Scan with the Bilibili mobile app and confirm login.'})
        previous = None
        while True:
            result = await active.poll(data['qrcode_key'])
            state = result.get('code')
            if state == 0:
                credential = parse_credential(result)
                await active.validate(credential)
                # Recheck to avoid replacing a session created while we were polling.
                if target.exists() and not args.replace:
                    raise SafeError('credential_exists', 'Session file appeared during login; it was preserved.')
                target.parent.mkdir(parents=True, exist_ok=True)
                if not args.credential_file and not os.environ.get('BILI_AGENT_CREDENTIAL_FILE'):
                    target.parent.chmod(0o700)
                if args.replace:
                    save_private(target, credential)
                else:
                    fd, temporary = tempfile.mkstemp(prefix='.session-', dir=target.parent)
                    try:
                        with os.fdopen(fd, 'w') as out:
                            json.dump(credential, out)
                        try:
                            os.link(temporary, target)  # Atomic create; never overwrite a concurrent session.
                        except FileExistsError:
                            raise SafeError('credential_exists', 'Session file appeared during login; it was preserved.') from None
                    finally:
                        os.unlink(temporary)
                emit('done', {'session': 'valid', 'credential_file': str(target.resolve()), 'credential_saved': True})
                return 0
            if state == 86038:
                emit('expired', {'credential_saved': False}, ok=False)
                return 2
            if state not in {86101, 86090}:
                raise SafeError('login_state_unknown', 'Unexpected QR login state; no credentials saved.')
            name = 'waiting_scan' if state == 86101 else 'waiting_confirmation'
            if name != previous:
                emit(name)
                previous = name
            await asyncio.sleep(2)
    try:
        if backend:
            return await asyncio.wait_for(run(backend), args.timeout)
        import aiohttp
        proxy = selected_proxy()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20),
                cookie_jar=aiohttp.DummyCookieJar(), trust_env=False, headers={'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://www.bilibili.com/'}) as session:
            return await asyncio.wait_for(run(HttpBackend(session,proxy)), args.timeout)
    except asyncio.TimeoutError:
        emit('timeout', {'credential_saved': False}, ok=False)
        return 2
    finally:
        # Login QR is ephemeral and must not remain after completion/cancellation.
        if qr.exists():
            qr.unlink()
        if directory:
            directory.rmdir()
