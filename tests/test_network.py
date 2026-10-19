import os
import ssl
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import test_cli
from bili_agent import Client, AgentError
from bili_agent.auth import SafeError
from bili_agent.errors import safe_error
from bili_agent.network import normalize_proxy, selected_proxy, configure_sdk_proxy
from bili_agent.login import HttpBackend


class ProxyTests(unittest.TestCase):
    def test_bare_http_auth_and_ipv6(self):
        self.assertEqual(normalize_proxy(' 127.0.0.1:7890 '),'http://127.0.0.1:7890')
        self.assertEqual(normalize_proxy('user:password@[::1]:7890'),'http://user:password@[::1]:7890')
        self.assertEqual(normalize_proxy('https://proxy.example:8443'),'https://proxy.example:8443')

    def test_invalid_proxy_never_echoes_credentials(self):
        for value in ['socks5://user:private@host:1080','http://user:private@host:bad','http://host:0',
                      'http://host:65536','http://host/path','http://host?private','http://host/#private','http://']:
            with self.assertRaises(SafeError) as error:normalize_proxy(value)
            self.assertNotIn('private',str(error.exception))

    def test_explicit_override_environment_order_and_lowercase_priority(self):
        env={'https_proxy':'local:1','HTTPS_PROXY':'other:2','all_proxy':'other:3','http_proxy':'other:4'}
        self.assertEqual(selected_proxy(env),'http://local:1')
        env['BILI_AGENT_PROXY']=''
        self.assertEqual(selected_proxy(env),'')
        env['BILI_AGENT_PROXY']='explicit:5'
        self.assertEqual(selected_proxy(env),'http://explicit:5')
        self.assertEqual(selected_proxy({'ALL_PROXY':'local:3'}),'http://local:3')
        self.assertEqual(selected_proxy({'HTTP_PROXY':'local:4'}),'http://local:4')
        self.assertIsNone(selected_proxy({}))

    def test_bypass_is_not_silently_ignored(self):
        self.assertEqual(selected_proxy({'https_proxy':'local:1','NO_PROXY':'*'}),'')
        self.assertEqual(selected_proxy({'https_proxy':'local:1','NO_PROXY':'localhost,127.0.0.1'}),'http://local:1')
        with self.assertRaises(SafeError) as error:
            selected_proxy({'https_proxy':'local:1','NO_PROXY':'.bilibili.com'})
        self.assertEqual(error.exception.code,'proxy_bypass_unsupported')
        self.assertEqual(selected_proxy({'BILI_AGENT_PROXY':'local:1','NO_PROXY':'.bilibili.com'}),'http://local:1')

    def test_sdk_configuration_is_idempotent_and_keeps_ssl(self):
        values={'proxy':'','trust':True}
        settings=SimpleNamespace(get_proxy=lambda:values['proxy'],get_trust_env=lambda:values['trust'],
            set_proxy=Mock(side_effect=lambda v:values.update(proxy=v)),
            set_trust_env=Mock(side_effect=lambda v:values.update(trust=v)),set_verify_ssl=Mock())
        with patch.dict(os.environ,{'https_proxy':'local:7890'},clear=True), \
             patch('bilibili_api.utils.network.request_settings',settings):
            configure_sdk_proxy();configure_sdk_proxy()
            self.assertEqual(os.environ['https_proxy'],'local:7890')
        settings.set_proxy.assert_called_once_with('http://local:7890')
        settings.set_trust_env.assert_called_once_with(False)
        settings.set_verify_ssl.assert_not_called()

    def test_tls_error_has_actionable_fixed_text_without_raw_value(self):
        error=safe_error(ssl.SSLError('https://user:private@host'))
        self.assertEqual(error['code'],'tls_error')
        self.assertFalse(error['retryable'])
        self.assertNotIn('private',str(error))
        self.assertIn('certificate',error['message'])

    def test_cli_offline_and_dry_run_ignore_broken_proxy(self):
        with patch.dict(os.environ,{'BILI_AGENT_PROXY':'socks5://user:private@host'},clear=True):
            for args in [('capabilities',),('dm-send','123','text','--dry-run')]:
                code,data=test_cli.CliTests.run_cli(self,*args)
                self.assertEqual(code,0)
            code,data=test_cli.CliTests.run_cli(self,'video','BV13Apt6sEhK')
            self.assertEqual(code,1)
            self.assertEqual(data['error']['code'],'proxy_invalid')
            self.assertNotIn('private',str(data))


class NetworkIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_and_owned_http_share_a_normalized_local_proxy(self):
        import aiohttp
        from aiohttp import web
        from bilibili_api import Credential
        from bilibili_api.utils.network import Api, request_settings, get_client
        observed=[]
        async def proxy(request):
            observed.append(request.path)
            return web.json_response({'code':0,'data':{'via_proxy':True}})
        app=web.Application();app.router.add_route('*','/{tail:.*}',proxy)
        runner=web.AppRunner(app);await runner.setup()
        site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
        port=site._server.sockets[0].getsockname()[1]
        previous=(request_settings.get_proxy(),request_settings.get_trust_env(),
                  request_settings.get_enable_bili_ticket())
        try:
            with patch.dict(os.environ,{'https_proxy':f'127.0.0.1:{port}'},clear=True):
                configure_sdk_proxy()
                request_settings.set_enable_bili_ticket(False)
                credential=Credential(buvid3='test',buvid4='test')
                result=await Api(url='http://target.invalid/sdk',method='GET',credential=credential).result
                self.assertEqual(result,{'via_proxy':True})
                async with aiohttp.ClientSession(trust_env=False) as session:
                    backend=HttpBackend(session,selected_proxy())
                    self.assertEqual(await backend.request('http://target.invalid/login'),{'via_proxy':True})
                self.assertEqual(observed,['/sdk','/login'])
        finally:
            await get_client().close()
            request_settings.set_proxy(previous[0])
            request_settings.set_trust_env(previous[1])
            request_settings.set_enable_bili_ticket(previous[2])
            await runner.cleanup()

    async def test_sdk_entry_configures_before_accessing_session(self):
        client=Client()
        with patch('bili_agent.sdk.configure_sdk_proxy') as configure, \
             patch('bili_agent.sdk.load_credential',side_effect=SafeError('credential_missing','missing')):
            with self.assertRaises(AgentError):await client.user(123)
            configure.assert_called_once()
        await client.aclose()
