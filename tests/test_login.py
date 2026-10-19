import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bili_agent.auth import SafeError
from bili_agent.login import login, parse_credential


DONE = {'code': 0, 'url': 'https://passport.bilibili.com/callback?SESSDATA=private%252Cvalue&bili_jct=csrf&DedeUserID=123', 'refresh_token': 'refresh'}


class Backend:
    def __init__(self, states, valid=True):
        self.states = iter(states)
        self.valid = valid
        self.polls = 0

    async def generate(self):
        return {'url': 'https://account.bilibili.com/h5/account-h5/auth/scan-web?oauthKey=secret', 'qrcode_key': 'secret'}

    async def poll(self, key):
        assert key == 'secret'
        self.polls += 1
        return next(self.states)

    async def validate(self, credential):
        if not self.valid:
            raise SafeError('login_validation_failed', 'Validation failed')


def render(url, path):
    path.write_bytes(b'fake-png')


class LoginTests(unittest.IsolatedAsyncioTestCase):
    def args(self, directory, **kwargs):
        values = dict(credential_file=str(Path(directory)/'credential'), qr_file=Path(directory)/'qr.png',
                      output=None, replace=False, timeout=2)
        values.update(kwargs)
        return SimpleNamespace(**values)

    async def test_success_verified_private_and_not_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory)
            events = []
            with patch('bili_agent.login.asyncio.sleep', return_value=None):
                result = await login(args, Backend([{'code':86101}, {'code':86090}, DONE]), events.append, render)
            self.assertEqual(result, 0)
            self.assertEqual([e['event'] for e in events], ['qrcode','waiting_scan','waiting_confirmation','done'])
            self.assertNotIn('private%2Cvalue', str(events))
            self.assertNotIn('refresh_token', str(events))
            self.assertNotIn('oauthKey', str(events))
            self.assertEqual(Path(args.credential_file).stat().st_mode & 0o777, 0o600)
            self.assertFalse(args.qr_file.exists())

    async def test_expired_does_not_create_session(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory)
            self.assertEqual(await login(args, Backend([{'code':86038}]), lambda _:None, render), 2)
            self.assertFalse(Path(args.credential_file).exists())
            self.assertFalse(args.qr_file.exists())

    async def test_existing_session_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory)
            Path(args.credential_file).write_text('old')
            with self.assertRaises(SafeError):
                await login(args, Backend([DONE]), lambda _:None, render)
            self.assertEqual(Path(args.credential_file).read_text(), 'old')

    async def test_validation_failure_preserves_replaced_session(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory, replace=True)
            Path(args.credential_file).write_text('old')
            with self.assertRaises(SafeError):
                await login(args, Backend([DONE],valid=False), lambda _:None, render)
            self.assertEqual(Path(args.credential_file).read_text(), 'old')
            self.assertFalse(args.qr_file.exists())

    async def test_unknown_state_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory)
            with self.assertRaises(SafeError):
                await login(args, Backend([{'code':999}]), lambda _:None, render)
            self.assertFalse(Path(args.credential_file).exists())

    async def test_timeout_cleans_qr(self):
        class Slow(Backend):
            async def poll(self, key):
                await asyncio.sleep(1)
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory, timeout=.02)
            self.assertEqual(await login(args, Slow([]), lambda _:None, render), 2)
            self.assertFalse(args.qr_file.exists())
            self.assertFalse(Path(args.credential_file).exists())

    def test_modern_cookie_response(self):
        result = parse_credential({'url': 'https://account.bilibili.com/callback',
                                  '_response_cookies': {'SESSDATA':'cookie', 'bili_jct':'csrf', 'DedeUserID':'123'}})
        self.assertEqual(result['sessdata'], 'cookie')
        self.assertEqual(result['dedeuserid'], '123')

    def test_parse_retains_encoding_and_accepts_unfollowed_cross_domain_callback(self):
        self.assertEqual(parse_credential(DONE)['sessdata'], 'private%2Cvalue')
        cross = dict(DONE, url=DONE['url'].replace('https://passport.bilibili.com', 'http://passport.biligame.com'))
        self.assertEqual(parse_credential(cross)['dedeuserid'], '123')
        with self.assertRaises(SafeError):
            parse_credential(dict(DONE, url='not-a-callback'))
