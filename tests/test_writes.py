import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from bili_agent import Client, AgentError
from bili_agent.sdk import BilibiliTransport
import test_cli

BV = 'BV13Apt6sEhK'

class Credential:
    def has_sessdata(self): return True
    def has_bili_jct(self): return True

class WriteTests(unittest.IsolatedAsyncioTestCase):
    def client(self, credential=None, **kwargs):
        self.transport = type('Transport', (), {})()
        self.transport.video = AsyncMock(return_value={'aid':42})
        for name in ['post_comment','like_video','like_comment','like_dynamic','favorite_video','repost_dynamic']:
            setattr(self.transport,name,AsyncMock(return_value={'new_field':123}))
        return Client(credential=credential,transport=self.transport,**kwargs)

    async def test_all_previews_are_offline_and_require_no_session(self):
        with patch('bili_agent.sdk.load_credential',side_effect=AssertionError('credential access')):
            client = Client(transport=object())
            plans = [await client.post_comment(BV,'原样文本 ',root=3,parent=4,dry_run=True),
                     await client.like_video(BV,state=False,dry_run=True),
                     await client.like_comment(BV,4,dry_run=True),
                     await client.like_dynamic(123,dry_run=True),
                     await client.favorite_video(BV,add=[2,2],remove=[3],dry_run=True),
                     await client.repost_dynamic(123,'转发',dry_run=True)]
            self.assertTrue(all(p['request_sent'] is False for p in plans))
            self.assertEqual(plans[0]['parameters']['text'],'原样文本 ')
            self.assertEqual(plans[4]['parameters']['add'],[2])

    async def test_invalid_writes_never_access_credentials(self):
        with patch('bili_agent.sdk.load_credential',side_effect=AssertionError('credential access')):
            client = Client(transport=object())
            for call in [lambda:client.post_comment(BV,' '),lambda:client.post_comment(BV,'x',parent=1),
                         lambda:client.like_comment(BV,0),lambda:client.like_video(BV,state=1),
                         lambda:client.like_dynamic(True),lambda:client.favorite_video(BV),
                         lambda:client.favorite_video(BV,add=[1],remove=[1]),
                         lambda:client.favorite_video(BV,add='1'),lambda:client.favorite_video(BV,add=[True]),
                         lambda:client.repost_dynamic(1,''),lambda:client.like_video(BV,dry_run='yes')]:
                with self.assertRaises(AgentError) as caught: await call()
                self.assertEqual(caught.exception.code,'invalid_arguments')

    async def test_missing_or_incomplete_credentials_send_nothing(self):
        incomplete = Credential()
        incomplete.has_bili_jct=lambda:False
        for credential, code in [(None,'credential_missing'),(incomplete,'credential_incomplete')]:
            client=self.client(credential)
            with self.assertRaises(AgentError) as caught: await client.post_comment(BV,'text')
            self.assertEqual(caught.exception.code,code)
            self.assertEqual(caught.exception.error['outcome'],'not_sent')
            self.transport.video.assert_not_awaited()
            self.transport.post_comment.assert_not_awaited()

    async def test_writes_dispatch_once_and_preserve_upstream_results(self):
        credential=Credential();client=self.client(credential)
        self.assertEqual(await client.post_comment(BV,'text',root=8,parent=9),{'new_field':123})
        self.transport.post_comment.assert_awaited_once_with(42,'text',8,9,credential)
        await client.like_comment(BV,9,state=False)
        self.transport.like_comment.assert_awaited_once_with(42,9,False,credential)
        await client.like_video(BV,state=False)
        self.transport.like_video.assert_awaited_once_with(BV,False,credential)
        await client.like_dynamic(123)
        self.transport.like_dynamic.assert_awaited_once_with(123,True,credential)
        await client.favorite_video(BV,add=[3],remove=[4])
        self.transport.favorite_video.assert_awaited_once_with(BV,[3],[4],credential)
        await client.repost_dynamic(123,'text')
        self.transport.repost_dynamic.assert_awaited_once_with(123,'text',credential)

    async def test_preflight_failure_is_not_sent(self):
        client=self.client(Credential())
        self.transport.video.side_effect=TimeoutError('private')
        with self.assertRaises(AgentError) as caught: await client.post_comment(BV,'text')
        self.assertEqual(caught.exception.error['outcome'],'not_sent')
        self.assertFalse(caught.exception.error['retryable'])
        self.transport.post_comment.assert_not_awaited()

    async def test_mutation_timeout_is_uncertain_and_not_retried(self):
        client=self.client(Credential(),timeout=.01)
        async def slow(*args): await asyncio.sleep(10)
        self.transport.repost_dynamic.side_effect=slow
        with self.assertRaises(AgentError) as caught: await client.repost_dynamic(123)
        self.assertEqual(caught.exception.code,'timeout')
        self.assertEqual(caught.exception.error['outcome'],'unknown')
        self.assertFalse(caught.exception.error['retryable'])
        self.transport.repost_dynamic.assert_awaited_once()

    async def test_write_error_is_redacted_without_retry(self):
        client=self.client(Credential())
        self.transport.like_video.side_effect=RuntimeError('SESSDATA=private')
        with self.assertRaises(AgentError) as caught: await client.like_video(BV)
        self.assertNotIn('private',str(caught.exception.error))
        self.assertFalse(caught.exception.error['retryable'])
        self.transport.like_video.assert_awaited_once()

    async def test_upstream_transport_parameters_are_correct(self):
        transport=BilibiliTransport();cred=Credential()
        video=type('Video',(),{'like':AsyncMock(return_value={}), 'set_favorite':AsyncMock(return_value={})})()
        with patch('bilibili_api.video.Video',return_value=video) as constructor:
            await transport.like_video(BV,False,cred)
            constructor.assert_called_with(bvid=BV,credential=cred)
            video.like.assert_awaited_once_with(False)
            await transport.favorite_video(BV,[1],[2],cred)
            video.set_favorite.assert_awaited_once_with(add_media_ids=[1],del_media_ids=[2])
        with patch('bilibili_api.comment.send_comment',new_callable=AsyncMock) as send:
            await transport.post_comment(42,'text',3,4,cred)
            from bilibili_api.comment import CommentResourceType
            send.assert_awaited_once_with('text',42,CommentResourceType.VIDEO,root=3,parent=4,credential=cred)
        comment=type('Comment',(),{'like':AsyncMock()})()
        with patch('bilibili_api.comment.Comment',return_value=comment) as constructor:
            await transport.like_comment(42,4,False,cred)
            constructor.assert_called_once_with(42,CommentResourceType.VIDEO,4,credential=cred)
            comment.like.assert_awaited_once_with(False)
        dynamic=type('Dynamic',(),{'set_like':AsyncMock(), 'repost':AsyncMock()})()
        with patch('bilibili_api.dynamic.Dynamic',return_value=dynamic) as constructor:
            await transport.like_dynamic(123,False,cred)
            constructor.assert_called_with(123,credential=cred)
            dynamic.set_like.assert_awaited_once_with(False)
            await transport.repost_dynamic(123,'text',cred)
            dynamic.repost.assert_awaited_once_with(text='text')

class WriteCliTests(unittest.TestCase):
    run_cli=test_cli.CliTests.run_cli

    def test_cli_previews_never_load_sessions(self):
        with patch('bili_agent.sdk.load_credential',side_effect=AssertionError('credential access')), \
             patch('bili_agent.cli.load_credential',side_effect=AssertionError('credential access')):
            for args in [('post-comment',BV,'text','--root','3','--parent','4'),
                         ('like-video',BV,'--state','off'),('like-comment',BV,'4'),
                         ('like-dynamic','123'),('favorite-video',BV,'--add','3','--remove','4'),
                         ('repost-dynamic','123','--text','text')]:
                code,payload=self.run_cli(*args,'--dry-run')
                self.assertEqual(code,0)
                self.assertTrue(payload['dry_run'])
                self.assertFalse(payload['data']['request_sent'])
                self.assertEqual(payload['effect'],'account_write')

    def test_cli_execution_dispatches_correctly(self):
        with patch('bili_agent.sdk.Client.repost_dynamic',new_callable=AsyncMock,return_value={'id':8}) as call:
            code,payload=self.run_cli('repost-dynamic','123','--text','原样')
            call.assert_awaited_once_with(123,'原样',dry_run=False)
            self.assertEqual(code,0)
            self.assertEqual(payload['data'],{'id':8})
            self.assertFalse(payload['dry_run'])

    def test_write_output_failure_does_not_trigger_retry(self):
        with patch('bili_agent.sdk.Client.like_video',new_callable=AsyncMock,return_value={}) as call, \
             patch('bili_agent.cli.save_private',side_effect=OSError):
            code,payload=self.run_cli('like-video',BV,'--output','result')
            self.assertEqual(code,1)
            self.assertEqual(payload['error']['outcome'],'succeeded')
            self.assertFalse(payload['error']['retryable'])
            call.assert_awaited_once()

    def test_cli_write_timeout_reports_unknown_without_retry(self):
        with patch('bili_agent.cli.query',new_callable=AsyncMock,side_effect=TimeoutError) as call:
            code,payload=self.run_cli('like-video',BV)
            self.assertEqual(code,1)
            self.assertEqual(payload['error']['outcome'],'unknown')
            self.assertFalse(payload['error']['retryable'])
            call.assert_awaited_once()

    def test_write_session_output_collision_prevents_dispatch(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            session=Path(directory)/'session';session.write_text('private')
            with patch('bili_agent.sdk.Client.like_video',new_callable=AsyncMock) as call:
                code,payload=self.run_cli('--credential-file',str(session),'like-video',BV,'--output',str(session))
                call.assert_not_awaited()
            self.assertEqual(session.read_text(),'private')
            self.assertEqual(code,1)
            self.assertEqual(payload['error']['outcome'],'not_sent')
