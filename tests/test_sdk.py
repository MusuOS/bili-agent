import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from bili_agent import Client, AgentError
from bili_agent.cli import main


class SdkTests(unittest.IsolatedAsyncioTestCase):
    def client(self, **kwargs):
        self.transport = type('Transport', (), {})()
        return Client(credential=None,transport=self.transport,**kwargs)

    async def test_search_preserves_raw_fields_and_dispatches_parameters(self):
        client = self.client()
        raw = {'result':[{'bvid':'BV13Apt6sEhK','title':'<em>Python</em>','new_field':42}],
               'numPages':3,'numResults':50}
        self.transport.search = AsyncMock(return_value=raw)
        result = await client.search(' Python ',page=2,size=2,order='pubdate')
        self.assertIs(result,raw)
        self.transport.search.assert_awaited_once_with('Python',2,2,'pubdate',None)

    async def test_invalid_parameters_do_not_load_credentials_or_call_transport(self):
        with patch('bili_agent.sdk.load_credential',side_effect=AssertionError('credential access')):
            async with Client(transport=object()) as client:
                for call in [lambda:client.search(''),lambda:client.user(0),
                             lambda:client.user_videos(1,size=21),lambda:client.user_dynamics(1,offset=123),
                             lambda:client.video('https://evil.example/video/BV13Apt6sEhK')]:
                    with self.assertRaises(AgentError):
                        await call()

    async def test_timeout_is_redacted_and_cancelled(self):
        cancelled = asyncio.Event()
        async def slow(*args):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()
        client=self.client(timeout=.01)
        self.transport.user=slow
        with self.assertRaises(AgentError) as caught:
            await client.user(1)
        self.assertEqual(caught.exception.code,'timeout')
        self.assertTrue(cancelled.is_set())

    async def test_api_error_does_not_expose_raw_exception(self):
        class Failure(Exception):
            code=-101
        client=self.client()
        self.transport.user=AsyncMock(side_effect=Failure('SESSDATA=private'))
        with self.assertRaises(AgentError) as caught:
            await client.user(1)
        self.assertEqual(caught.exception.code,'session_invalid')
        self.assertNotIn('private',str(caught.exception.error))

    async def test_comments_resolves_aid_then_fetches_requested_page(self):
        client=self.client()
        self.transport.video=AsyncMock(return_value={'aid':42})
        self.transport.comments=AsyncMock(return_value={'replies':[]})
        await client.comments('BV13Apt6sEhK',page=2,sort='time')
        self.transport.comments.assert_awaited_once_with(42,2,'time',None)

    async def test_closed_client_rejects_calls_without_transport_access(self):
        client=self.client()
        await client.aclose()
        await client.aclose()
        with self.assertRaises(AgentError) as caught:
            await client.video('BV13Apt6sEhK')
        self.assertEqual(caught.exception.code,'client_closed')

    async def test_missing_video_aid_has_stable_error(self):
        client=self.client()
        self.transport.video=AsyncMock(return_value={'title':'incomplete'})
        with self.assertRaises(AgentError) as caught:
            await client.replies('BV13Apt6sEhK',1)
        self.assertEqual(caught.exception.code,'response_invalid')

    async def test_dynamics_passes_cursor_unchanged(self):
        client=self.client()
        self.transport.user_dynamics=AsyncMock(return_value={'offset':'next','has_more':True,'items':[]})
        result=await client.user_dynamics(42,offset='previous')
        self.transport.user_dynamics.assert_awaited_once_with(42,'previous',None)
        self.assertEqual(result['offset'],'next')

    async def test_caller_cancellation_propagates(self):
        client=self.client()
        self.transport.user=AsyncMock(side_effect=asyncio.CancelledError)
        with self.assertRaises(asyncio.CancelledError):
            await client.user(1)
