import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import test_cli
from bili_agent import Client, AgentError
from bili_agent.sdk import BilibiliTransport
from test_writes import Credential

BV='BV13Apt6sEhK'

class BasicSdkTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_write_previews_never_read_credentials(self):
        with patch('bili_agent.sdk.load_credential',side_effect=AssertionError('credential access')):
            client=Client(transport=object())
            calls=[client.live_send(123,'text',reply_uid=4,dry_run=True),
                   client.video_send_danmaku(BV,'text',time=2.5,part=2,color='AA00FF',mode=4,dry_run=True),
                   client.follow_user(4,state=False,dry_run=True),client.block_user(4,state=False,dry_run=True),
                   client.watch_later_set(BV,state=False,dry_run=True),client.coin_video(BV,count=2,dry_run=True),
                   client.post_dynamic('plain @name',dry_run=True)]
            plans=[await call for call in calls]
            self.assertTrue(all(p['request_sent'] is False for p in plans))
            self.assertEqual(plans[1]['parameters']['color'],'aa00ff')
            self.assertEqual(plans[1]['parameters']['part'],2)

    async def test_invalid_new_inputs_never_load_credentials(self):
        with patch('bili_agent.sdk.load_credential',side_effect=AssertionError('credential access')):
            client=Client(transport=object())
            for call in [lambda:client.live_send(0,'text'),lambda:client.live_send(1,'text',reply_uid=True),
                         lambda:client.live_send(1,' '),lambda:client.video_send_danmaku(BV,'text',time=float('nan')),
                         lambda:client.video_send_danmaku(BV,'text',time=float('inf')),
                         lambda:client.video_send_danmaku(BV,'text',time=True),
                         lambda:client.video_send_danmaku(BV,'text',color='special'),
                         lambda:client.video_send_danmaku(BV,'text',mode=True),
                         lambda:client.video_send_danmaku(BV,'text',part=0),
                         lambda:client.follow_user(True),lambda:client.block_user(1,state='on'),
                         lambda:client.coin_video(BV,count=3),lambda:client.coin_video(BV,count=True),
                         lambda:client.coin_video(BV,like=1),lambda:client.post_dynamic(''),
                         lambda:client.dynamic(0),lambda:client.video_danmaku(BV,segment=0),
                         lambda:client.user_relation(0)]:
                with self.assertRaises(AgentError): await call()

    async def test_all_write_parameters_are_dispatched_once(self):
        names=['live_send','video_send_danmaku','follow_user','block_user','watch_later_set','coin_video','post_dynamic']
        transport=SimpleNamespace(**{n:AsyncMock(return_value={'raw':7}) for n in names})
        cred=Credential();client=Client(credential=cred,transport=transport)
        await client.live_send(123,'text',reply_uid=4)
        transport.live_send.assert_awaited_once_with(123,'text',4,cred)
        await client.video_send_danmaku(BV,'text',time=1.5,part=2,color='AA00FF',mode=5)
        transport.video_send_danmaku.assert_awaited_once_with(BV,'text',1.5,2,'aa00ff',5,cred)
        await client.follow_user(4,state=False)
        transport.follow_user.assert_awaited_once_with(4,False,cred)
        await client.block_user(4,state=False)
        transport.block_user.assert_awaited_once_with(4,False,cred)
        await client.watch_later_set(BV,state=False)
        transport.watch_later_set.assert_awaited_once_with(BV,False,cred)
        await client.coin_video(BV,count=2,like=True)
        transport.coin_video.assert_awaited_once_with(BV,2,True,cred)
        self.assertEqual(await client.post_dynamic('text'),{'raw':7})
        transport.post_dynamic.assert_awaited_once_with('text',cred)

    async def test_read_primitives_dispatch_and_preserve_data(self):
        raw={'unknown_field':42}
        transport=SimpleNamespace(**{n:AsyncMock(return_value=raw) for n in
                                  ['dynamic','video_parts','user_relation','video_state','video_danmaku']})
        cred=Credential();client=Client(credential=cred,transport=transport)
        self.assertIs(await client.dynamic(123),raw)
        transport.dynamic.assert_awaited_once_with(123,cred)
        self.assertIs(await client.video_parts(BV),raw)
        self.assertIs(await client.user_relation(4),raw)
        transport.user_relation.assert_awaited_once_with(4,cred)
        self.assertIs(await client.video_state(BV),raw)
        self.assertIs(await client.video_danmaku(BV,part=2,segment=3),raw)
        transport.video_danmaku.assert_awaited_once_with(BV,2,3,cred)

    async def test_account_reads_require_session_and_reject_closed_client(self):
        client=Client(credential=None,transport=object())
        for call in [lambda:client.video_state(BV),lambda:client.user_relation(4)]:
            with self.assertRaises(AgentError) as error: await call()
            self.assertEqual(error.exception.code,'credential_missing')
        await client.aclose()
        with self.assertRaises(AgentError) as error:await client.user_relation(4)
        self.assertEqual(error.exception.code,'client_closed')

    async def test_follow_and_block_map_only_requested_relation_actions(self):
        from bilibili_api.user import RelationType
        owner=SimpleNamespace(modify_relation=AsyncMock(return_value={}),get_relation=AsyncMock(return_value={'attribute':2}))
        transport=BilibiliTransport();cred=Credential()
        with patch('bilibili_api.user.User',return_value=owner) as constructor:
            for method,states in [('follow_user',[RelationType.SUBSCRIBE,RelationType.UNSUBSCRIBE]),
                                  ('block_user',[RelationType.BLOCK,RelationType.UNBLOCK])]:
                for state,expected in zip([True,False],states):
                    await getattr(transport,method)(4,state,cred)
                    owner.modify_relation.assert_awaited_with(expected)
            constructor.assert_called_with(4,credential=cred)
            self.assertEqual(await transport.user_relation(4,cred),{'attribute':2})

    async def test_live_transport_resolves_room_and_preserves_text(self):
        room=SimpleNamespace(send_danmaku=AsyncMock(return_value={'sent':True}))
        with patch('bilibili_api.live.LiveRoom',return_value=room) as constructor:
            self.assertEqual(await BilibiliTransport().live_send(123,'text',4,None),{'sent':True})
            constructor.assert_called_once_with(123,credential=None)
            args,kwargs=room.send_danmaku.await_args
            self.assertEqual(args[0].text,'text')
            self.assertEqual(kwargs,{'reply_mid':4})
            # No room_id override: upstream must resolve short IDs.

    async def test_video_part_and_segment_translation(self):
        danmaku=SimpleNamespace(id_=7,id_str='7',text='text',dm_time=2.5,color='ffffff',mode=1,font_size=25,send_time=123)
        item=SimpleNamespace(send_danmaku=AsyncMock(return_value={}), get_danmakus=AsyncMock(return_value=[danmaku]),
                             get_pages=AsyncMock(return_value=[{'cid':7}]))
        with patch('bilibili_api.video.Video',return_value=item):
            transport=BilibiliTransport()
            await transport.video_send_danmaku(BV,'text',2.5,2,'aa00ff',4,None)
            args=item.send_danmaku.await_args.kwargs
            self.assertEqual(args['page_index'],1)
            self.assertEqual(args['danmaku'].dm_time,2.5)
            self.assertEqual(args['danmaku'].color,'aa00ff')
            self.assertEqual(args['danmaku'].mode,4)
            result=await transport.video_danmaku(BV,2,3,None)
            item.get_danmakus.assert_awaited_once_with(page_index=1,from_seg=2,to_seg=2)
            self.assertEqual(result['scope'],'one_segment')
            self.assertEqual(result['items'][0]['id'],7)
            self.assertEqual(result['items'][0]['time'],2.5)
            self.assertEqual(await transport.video_parts(BV,None),[{'cid':7}])

    async def test_video_state_watch_later_and_coin_routes(self):
        item=SimpleNamespace(has_liked=AsyncMock(return_value=1),has_favoured=AsyncMock(return_value=False),
                             get_pay_coins=AsyncMock(return_value=2),add_to_toview=AsyncMock(return_value={}),
                             delete_from_toview=AsyncMock(return_value={}),pay_coin=AsyncMock(return_value={}))
        with patch('bilibili_api.video.Video',return_value=item):
            transport=BilibiliTransport()
            self.assertEqual(await transport.video_state(BV,None),{'liked':True,'favoured':False,'coins':2})
            await transport.watch_later_set(BV,True,None)
            await transport.watch_later_set(BV,False,None)
            item.add_to_toview.assert_awaited_once()
            item.delete_from_toview.assert_awaited_once()
            await transport.coin_video(BV,2,False,None)
            item.pay_coin.assert_awaited_once_with(num=2,like=False)

    async def test_plain_dynamic_preserves_text_without_mention_parsing(self):
        transport=BilibiliTransport();cred=Credential()
        with patch('bilibili_api.dynamic.send_dynamic',new_callable=AsyncMock,return_value={'id':7}) as send:
            result=await transport.post_dynamic('@name [emoji] ',cred)
            self.assertEqual(result,{'id':7})
            content=send.await_args.args[0]
            self.assertEqual(content.contents,[{'biz_id':'','type':1,'raw_text':'@name [emoji] '}])
            self.assertEqual(content.pics,[])
            self.assertEqual(send.await_args.kwargs,{'credential':cred})
        item=SimpleNamespace(get_info=AsyncMock(return_value={'id_str':'123'}))
        with patch('bilibili_api.dynamic.Dynamic',return_value=item) as constructor:
            self.assertEqual(await transport.dynamic(123,cred),{'id_str':'123'})
            constructor.assert_called_once_with(123,credential=cred)

class BasicCliTests(unittest.TestCase):
    run_cli=test_cli.CliTests.run_cli

    def test_new_cli_previews_with_missing_session(self):
        with patch('bili_agent.sdk.load_credential',side_effect=AssertionError('credential access')):
            for args in [('live-send','123','text','--reply-uid','4'),('video-send-danmaku',BV,'text','--time','2.5','--part','2'),
                         ('follow-user','4','--state','off'),('block-user','4','--state','off'),
                         ('watch-later-set',BV,'--state','off'),('coin-video',BV,'--count','2'),('post-dynamic','text')]:
                code,payload=self.run_cli(*args,'--dry-run')
                self.assertEqual(code,0)
                self.assertFalse(payload['data']['request_sent'])
                self.assertEqual(payload['route'],'local')

    def test_live_send_dispatch_from_cli(self):
        with patch('bili_agent.sdk.Client.live_send',new_callable=AsyncMock,return_value={}) as call:
            code,payload=self.run_cli('live-send','123','text','--reply-uid','4')
            self.assertEqual(code,0)
            self.assertEqual(payload['effect'],'account_write')
            call.assert_awaited_once_with(123,'text',reply_uid=4,dry_run=False)

    def test_state_and_video_reads_cli_dispatch(self):
        with patch('bili_agent.cli.load_credential',return_value=Credential()):
            for args,method,expected in [(('dynamic','123'),'dynamic',(123,)),
                                         (('user-relation','4'),'user_relation',(4,)),
                                         (('video-state',BV),'video_state',(BV,)),
                                         (('video-parts',BV),'video_parts',(BV,))]:
                with patch('bili_agent.sdk.Client.'+method,new_callable=AsyncMock,return_value={}) as call:
                    code,payload=self.run_cli(*args)
                    self.assertEqual(code,0)
                    call.assert_awaited_once_with(*expected)
            with patch('bili_agent.sdk.Client.video_danmaku',new_callable=AsyncMock,return_value={}) as call:
                code,payload=self.run_cli('video-danmaku',BV,'--part','2','--segment','3')
                self.assertEqual(code,0)
                call.assert_awaited_once_with(BV,part=2,segment=3)
