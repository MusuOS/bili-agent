import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import test_cli
from test_writes import Credential
from bili_agent import Client, AgentError
from bili_agent import messaging
from bili_agent.sdk import BilibiliTransport


class MessagingTests(unittest.IsolatedAsyncioTestCase):
    def client(self, credential=None, **kwargs):
        names=['dm_sessions','dm_history','dm_new','dm_session','dm_send']
        self.transport=SimpleNamespace(**{n:AsyncMock(return_value={'unknown_field':42}) for n in names})
        return Client(credential=credential,transport=self.transport,**kwargs)

    async def test_read_parameters_preserve_raw_fields_and_cursor_zero(self):
        credential=Credential();client=self.client(credential)
        raw={'session_list':[], 'has_more':1, 'unknown_field':42}
        self.transport.dm_sessions.return_value=raw
        self.assertIs(await client.dm_sessions(size=2,kind=8,before_ts=1234567890000000),raw)
        self.transport.dm_sessions.assert_awaited_once_with(2,8,1234567890000000,credential)
        await client.dm_history(123,size=2,after_seq=0)
        self.transport.dm_history.assert_awaited_once_with(123,2,0,None,credential)
        await client.dm_new(0,size=2)
        self.transport.dm_new.assert_awaited_once_with(0,2,credential)
        await client.dm_session(123)
        self.transport.dm_session.assert_awaited_once_with(123,credential)

    async def test_invalid_inputs_never_load_credentials(self):
        with patch('bili_agent.sdk.load_credential',side_effect=AssertionError('credential access')):
            client=Client(transport=object())
            for call in [lambda:client.dm_sessions(size=21),lambda:client.dm_sessions(kind=True),
                         lambda:client.dm_sessions(kind=10),lambda:client.dm_sessions(before_ts=-1),
                         lambda:client.dm_history(0),lambda:client.dm_history(1,after_seq=True),
                         lambda:client.dm_history(1,after_seq=1,before_seq=2),
                         lambda:client.dm_history(1,before_seq=-1),lambda:client.dm_new(-1),
                         lambda:client.dm_new(True),lambda:client.dm_session(0),
                         lambda:client.dm_send(0,'text'),lambda:client.dm_send(1,' ')]:
                with self.assertRaises(AgentError):await call()

    async def test_anonymous_reads_send_nothing(self):
        client=self.client()
        for call in [lambda:client.dm_sessions(),lambda:client.dm_history(123),
                     lambda:client.dm_new(0),lambda:client.dm_session(123)]:
            with self.assertRaises(AgentError) as error: await call()
            self.assertEqual(error.exception.code,'credential_missing')
        for name in ['dm_sessions','dm_history','dm_new','dm_session']:
            getattr(self.transport,name).assert_not_awaited()

    async def test_dry_run_does_not_access_session_or_transport(self):
        with patch('bili_agent.sdk.load_credential',side_effect=AssertionError('credential access')):
            client=Client(transport=object())
            plan=await client.dm_send(123,'原样\n"文字" ',dry_run=True)
            self.assertEqual(plan['parameters'],{'uid':123,'text':'原样\n"文字" '})
            self.assertFalse(plan['request_sent'])

    async def test_send_success_and_timeout_are_not_retried(self):
        credential=Credential();client=self.client(credential,timeout=.01)
        self.assertEqual(await client.dm_send(123,'text'),{'unknown_field':42})
        self.transport.dm_send.assert_awaited_once_with(123,'text',credential)
        async def slow(*args):await asyncio.sleep(10)
        self.transport.dm_send.reset_mock()
        self.transport.dm_send.side_effect=slow
        with self.assertRaises(AgentError) as error:await client.dm_send(123,'text')
        self.assertEqual(error.exception.error['outcome'],'unknown')
        self.assertFalse(error.exception.error['retryable'])
        self.transport.dm_send.assert_awaited_once()

    async def test_api_read_payloads_and_omitted_cursor(self):
        from bilibili_api.utils.network import Api
        seen=[]
        async def request(api,*args,**kwargs):
            seen.append((api.url,dict(api.params)))
            return {'raw':42}
        with patch.object(Api,'request',request):
            self.assertEqual(await messaging.sessions(2,8,123,None),{'raw':42})
            self.assertEqual(seen[-1][1]['end_ts'],123)
            self.assertEqual(seen[-1][1]['session_type'],8)
            await messaging.history(4,2,None,None,None)
            self.assertNotIn('begin_seqno',seen[-1][1])
            self.assertNotIn('end_seqno',seen[-1][1])
            self.assertEqual(seen[-1][1]['session_type'],1)
            await messaging.history(4,2,0,None,None)
            self.assertEqual(seen[-1][1]['begin_seqno'],0)
            await messaging.history(4,2,None,9,None)
            self.assertEqual(seen[-1][1]['end_seqno'],9)
            await messaging.new(1234567890000000,2,None)
            self.assertEqual(seen[-1][1]['begin_ts'],1234567890000000)
            self.assertEqual(seen[-1][1]['size'],2)
            await messaging.detail(4,None)
            self.assertEqual(seen[-1][1]['talker_id'],4)
        self.assertTrue(all('update_ack' not in url and 'send_msg' not in url for url,_ in seen))

    async def test_sender_identity_and_text_payload_use_single_attempt(self):
        from bilibili_api.utils.network import Api
        from bilibili_api.exceptions import ResponseCodeException
        seen=[]
        async def once(api,*args,**kwargs):
            seen.append(api)
            raise ResponseCodeException(-403,'secret response')
        client=Client(credential=Credential())
        with patch('bilibili_api.user.get_self_info',new_callable=AsyncMock,return_value={'mid':7}), \
             patch.object(Api,'_request',once), \
             patch.object(Api,'request',side_effect=AssertionError('retry wrapper used')):
            with self.assertRaises(AgentError) as error:
                await client.dm_send(4,'原样\n"文字" ')
            self.assertEqual(len(seen),1)
            api=seen[0]
            self.assertTrue(api.wbi)
            self.assertEqual(api.params,{'w_sender_uid':7,'w_receiver_id':4})
            self.assertEqual(api.data['msg[sender_uid]'],7)
            self.assertEqual(api.data['msg[receiver_id]'],4)
            self.assertEqual(api.data['msg[msg_type]'],1)
            self.assertEqual(json.loads(api.data['msg[content]']),{'content':'原样\n"文字" '})
            self.assertFalse(error.exception.error['retryable'])
            self.assertEqual(error.exception.error['outcome'],'unknown')
            self.assertNotIn('secret',str(error.exception.error))
            client._owns_transport=False # No actual SDK session was created in this fixture.

    async def test_bad_sender_identity_prevents_post(self):
        from bilibili_api.utils.network import Api
        with patch('bilibili_api.user.get_self_info',new_callable=AsyncMock,return_value={'mid':True}), \
             patch.object(Api,'_request',new_callable=AsyncMock) as post:
            with self.assertRaises(Exception) as error:await messaging.send(4,'text',None)
            self.assertEqual(error.exception.code,'response_invalid')
            post.assert_not_awaited()

    async def test_transport_delegates_all_five_primitives(self):
        transport=BilibiliTransport();cred=Credential()
        for method,function,args in [('dm_sessions','sessions',(2,8,123)),('dm_history','history',(4,2,0,None)),
                                     ('dm_new','new',(123,2)),('dm_session','detail',(4,)),('dm_send','send',(4,'text'))]:
            with patch('bili_agent.messaging.'+function,new_callable=AsyncMock,return_value={'raw':42}) as call:
                self.assertEqual(await getattr(transport,method)(*args,cred),{'raw':42})
                call.assert_awaited_once_with(*args,cred)


class MessagingCliTests(unittest.TestCase):
    run_cli=test_cli.CliTests.run_cli

    def test_cli_send_preview_is_offline(self):
        with patch('bili_agent.sdk.load_credential',side_effect=AssertionError('credential access')), \
             patch('bili_agent.cli.load_credential',side_effect=AssertionError('credential access')):
            code,payload=self.run_cli('dm-send','4','text','--dry-run')
        self.assertEqual(code,0)
        self.assertFalse(payload['data']['request_sent'])

    def test_all_cli_parameters_dispatch(self):
        cases=[(('dm-sessions','--kind','8','--size','2','--before-ts','123'),'dm_sessions',(),{'size':2,'kind':8,'before_ts':123}),
               (('dm-history','4','--after-seq','0','--size','2'),'dm_history',(4,),{'size':2,'after_seq':0,'before_seq':None}),
               (('dm-history','4','--before-seq','9'),'dm_history',(4,),{'size':20,'after_seq':None,'before_seq':9}),
               (('dm-new','123','--size','2'),'dm_new',(123,),{'size':2}),
               (('dm-session','4'),'dm_session',(4,),{}),
               (('dm-send','4','text'),'dm_send',(4,'text'),{'dry_run':False})]
        with patch('bili_agent.cli.load_credential',return_value=Credential()):
            for args,method,positional,kwargs in cases:
                with patch('bili_agent.sdk.Client.'+method,new_callable=AsyncMock,return_value={'raw':42}) as call:
                    code,payload=self.run_cli(*args)
                    self.assertEqual(code,0)
                    call.assert_awaited_once_with(*positional,**kwargs)

    def test_conflicting_message_cursors_are_rejected_without_echo(self):
        code,payload=self.run_cli('dm-history','4','--after-seq','1','--before-seq','2')
        self.assertEqual(code,1)
        self.assertEqual(payload['error']['code'],'invalid_arguments')
