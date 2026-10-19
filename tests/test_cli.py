import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bili_agent.cli import main, bvid, safe_error
from bili_agent.auth import SafeError, load_credential
from bili_agent.collect import save_private


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with patch('sys.argv', ['bili-agent', *args]), contextlib.redirect_stdout(out):
            try:
                code = main()
            except SystemExit as exc:
                code = exc.code
        return code, json.loads(out.getvalue())

    def test_capabilities_without_credentials_or_network(self):
        with patch('bili_agent.cli.load_credential', side_effect=AssertionError('credential access')):
            code, data = self.run_cli('capabilities')
        self.assertEqual(code, 0)
        self.assertTrue(data['data']['account_writes'])
        self.assertEqual(len(data['data']['commands']), 48)

    def test_missing_session_is_actionable(self):
        with tempfile.TemporaryDirectory() as directory:
            code, data = self.run_cli('--credential-file', str(Path(directory)/'missing'), 'status')
        self.assertEqual(code, 1)
        self.assertEqual(data['error']['code'], 'credential_missing')

    def test_bad_session_is_preserved_without_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'session'
            path.write_text('secret-not-json')
            code, data = self.run_cli('--credential-file', str(path), 'status')
            self.assertEqual(path.read_text(), 'secret-not-json')
        self.assertEqual(code, 1)
        self.assertNotIn('secret-not-json', json.dumps(data))

    def test_invalid_arguments_do_not_echo_values(self):
        code, data = self.run_cli('secret-cookie')
        self.assertEqual(code, 1)
        self.assertNotIn('secret-cookie', json.dumps(data))

    def test_output_cannot_overwrite_session(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'session'
            path.write_text('secret')
            code, data = self.run_cli('--credential-file', str(path), 'capabilities', '--output', str(path))
            self.assertEqual(path.read_text(), 'secret')
        self.assertEqual(code, 1)
        self.assertEqual(data['error']['code'], 'unsafe_output')

    def test_video_host_is_validated(self):
        self.assertEqual(bvid('https://www.bilibili.com/video/BV13Apt6sEhK/?x=1'), 'BV13Apt6sEhK')
        with self.assertRaises(SafeError):
            bvid('https://evil.example/video/BV13Apt6sEhK')

    def test_error_text_is_not_exposed(self):
        self.assertNotIn('cookie=secret', json.dumps(safe_error(RuntimeError('cookie=secret'))))

    def test_output_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'out'
            save_private(path, {'ok': True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(json.loads(path.read_text())['ok'])
