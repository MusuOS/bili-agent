import argparse
import asyncio
import json
import sys
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

from . import __version__
from .errors import safe_error
from .identifiers import bvid
from .auth import SafeError, credential_path, load_credential
from .collect import collect, save_private
from .network import configure_sdk_proxy

DM_READS = {'dm-sessions','dm-history','dm-new','dm-session'}
NEW_WRITES = {'dm-send','live-send','video-send-danmaku','follow-user','block-user','watch-later-set','coin-video','post-dynamic'}
NEW_READS = DM_READS | {'dynamic','video-state','user-relation','video-parts','video-danmaku'}
WRITES = NEW_WRITES | {'post-comment','like-video','like-comment','like-dynamic','favorite-video','repost-dynamic'}
ACCOUNT = DM_READS | {'status', 'whoami', 'history', 'favorites', 'following', 'watch-later', 'my-dynamics', 'feed', 'video-state','user-relation'}
VIDEO = {'video', 'related', 'subtitles', 'comments', 'replies', 'all-comments', 'all-replies','video-state','video-parts','video-danmaku'}
COMMANDS = ['capabilities', 'doctor', 'status', 'whoami', 'video', 'related', 'subtitles',
            'hot', 'history', 'favorites', 'following', 'watch-later', 'my-dynamics', 'feed',
            'comments', 'replies', 'all-comments', 'all-replies', 'live-info', 'live-watch', 'login', 'search', 'user', 'user-videos', 'user-dynamics', 'post-comment', 'like-video', 'like-comment', 'like-dynamic', 'favorite-video', 'repost-dynamic', *sorted(NEW_READS | NEW_WRITES)]


def envelope(command, data=None, error=None):
    value = {'schema_version': 1, 'ok': error is None, 'command': command,
             'route': 'local' if command in {'capabilities', 'doctor'} else 'pure-http'}
    value['error' if error else 'data'] = error if error else data
    return value


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # Fixed text avoids reflecting accidental credentials passed as arguments.
        print(json.dumps(envelope(None, error={'code': 'invalid_arguments',
              'message': 'Invalid command or arguments. Run bili-agent --help.', 'retryable': False})))
        raise SystemExit(1)


def parser():
    p = Parser(description='Bilibili primitive tools for agents. JSON output by default.')
    p.add_argument('--version', action='version', version=__version__)
    p.add_argument('--credential-file', help='Local credential JSON (only login writes it)')
    p.add_argument('--summary', action='store_true', help='Print counts/status only; combine with --output')
    subs = p.add_subparsers(dest='command', required=True)
    for name in COMMANDS:
        example = ('bili-agent '+name+' --dry-run' if name in WRITES else 'bili-agent '+name)
        if name in VIDEO or name in {'post-comment','like-video','like-comment','favorite-video','video-send-danmaku','watch-later-set','coin-video'}:
            example = 'bili-agent '+name+' BV13Apt6sEhK'
        if name in {'replies','all-replies','like-comment'}:
            example += ' 123'
        if name in {'post-comment','video-send-danmaku'}:
            example += ' "要发送的文字"'
        if name in {'user','user-videos','user-dynamics','follow-user','block-user','user-relation','dm-history','dm-session','dm-send'}:
            example = 'bili-agent '+name+' 123'
        if name in {'like-dynamic','dynamic','repost-dynamic','live-info','live-watch','live-send'}:
            example = 'bili-agent '+name+' 123'
        if name in {'live-send','dm-send'}:
            example += ' "要发送的文字"'
        if name == 'post-dynamic':
            example = 'bili-agent post-dynamic "纯文字动态"'
        if name == 'search':
            example = 'bili-agent search Python --size 2'
        if name == 'dm-new':
            example = 'bili-agent dm-new 1791590400000000 --size 2'
        if name == 'favorite-video':
            example += ' --add 123'
        if name in WRITES and not example.endswith('--dry-run'):
            example += ' --dry-run'
        if name == 'related':
            example += '\n  bili-agent related https://www.bilibili.com/video/BV13Apt6sEhK/'
        note = '\n检查 data.complete 和 issues；total 数不能证明评论完整。' if name in {'all-comments','all-replies'} else ''
        s = subs.add_parser(name,formatter_class=argparse.RawDescriptionHelpFormatter,
                            epilog='示例：\n  '+example+note)
        s.add_argument('--output', type=Path)
        if name in {'dm-history','dm-session','dm-send'}:
            s.add_argument('uid',type=int)
        if name == 'dm-send':
            s.add_argument('text')
        if name in {'dm-sessions','dm-history','dm-new'}:
            s.add_argument('--size',type=int,default=20)
        if name == 'dm-sessions':
            s.add_argument('--kind',type=int,choices=range(1,10),default=1)
            s.add_argument('--before-ts',type=int,help='Microsecond end timestamp')
        if name == 'dm-history':
            cursor=s.add_mutually_exclusive_group()
            cursor.add_argument('--after-seq',type=int,help='Fetch messages after this sequence number')
            cursor.add_argument('--before-seq',type=int,help='Fetch messages before this sequence number')
        if name == 'dm-new':
            s.add_argument('since',type=int,help='Microsecond timestamp of last observed session activity')
        if name in WRITES:
            s.add_argument('--dry-run', action='store_true', help='Preview validated operation without credentials or network')
        if name in {'post-comment','like-video','like-comment','favorite-video','video-send-danmaku','watch-later-set','coin-video'}:
            s.add_argument('video')
        if name in {'like-dynamic','repost-dynamic','dynamic'}:
            s.add_argument('dynamic_id',type=int)
        if name in {'like-video','like-comment','like-dynamic','follow-user','block-user','watch-later-set'}:
            s.add_argument('--state',choices=['on','off'],default='on')
        if name == 'like-comment':
            s.add_argument('rpid',type=int)
        if name in {'follow-user','block-user','user-relation'}:
            s.add_argument('uid',type=int)
        if name in {'video-send-danmaku','post-dynamic'}:
            s.add_argument('text')
        if name == 'live-send':
            s.add_argument('room',type=int)
            s.add_argument('text')
            s.add_argument('--reply-uid',type=int)
        if name == 'video-send-danmaku':
            s.add_argument('--time',type=float,default=0,help='Position in video, seconds')
            s.add_argument('--color',default='ffffff')
            s.add_argument('--mode',type=int,choices=[1,4,5],default=1)
        if name in {'video-send-danmaku','video-danmaku'}:
            s.add_argument('--part',type=int,default=1)
        if name == 'video-danmaku':
            s.add_argument('--segment',type=int,default=1,help='One 6-minute segment, numbered from 1')
        if name == 'coin-video':
            s.add_argument('--count',type=int,choices=[1,2],default=1)
            s.add_argument('--like',action='store_true')
        if name == 'post-comment':
            s.add_argument('text')
            s.add_argument('--root',type=int)
            s.add_argument('--parent',type=int)
        if name == 'repost-dynamic':
            s.add_argument('--text',default='转发动态')
        if name == 'favorite-video':
            s.add_argument('--add',type=int,nargs='+',default=[])
            s.add_argument('--remove',type=int,nargs='+',default=[])
        if name == 'search':
            s.add_argument('keyword')
            s.add_argument('--page', type=int, default=1)
            s.add_argument('--size', type=int, default=20)
            s.add_argument('--order', choices=['totalrank','click','pubdate','dm','stow'], default='totalrank')
        if name in {'user','user-videos','user-dynamics'}:
            s.add_argument('uid',type=int)
        if name == 'user-videos':
            s.add_argument('--page',type=int,default=1)
            s.add_argument('--size',type=int,default=20)
            s.add_argument('--keyword',default='')
            s.add_argument('--order',choices=['pubdate','click','stow'],default='pubdate')
        if name == 'user-dynamics':
            s.add_argument('--offset',default='')
        if name == 'login':
            s.add_argument('--timeout', type=float, default=180)
            s.add_argument('--qr-file', type=Path)
            s.add_argument('--replace', action='store_true')
        if name in VIDEO:
            s.add_argument('video')
        if name in {'replies', 'all-replies'}:
            s.add_argument('root', type=int)
        if name in {'comments', 'replies', 'hot', 'history', 'following', 'favorites', 'feed'}:
            s.add_argument('--page', type=int, default=1)
        if name in {'replies', 'hot', 'history', 'following'}:
            s.add_argument('--size', type=int, default=20)
        if name == 'comments':
            s.add_argument('--sort', choices=['time', 'like'], default='like')
        if name in {'all-comments', 'all-replies'}:
            s.add_argument('--max-pages', type=int, default=200)
            s.add_argument('--delay', type=float, default=1)
        if name in {'my-dynamics', 'feed'}:
            s.add_argument('--offset', default='')
        if name == 'favorites':
            s.add_argument('--folder', type=int)
        if name == 'subtitles':
            s.add_argument('--part', type=int, default=1)
            s.add_argument('--language', help='Fetch selected subtitle body by language code; otherwise list tracks')
        if name in {'live-info', 'live-watch'}:
            s.add_argument('room', type=int)
        if name == 'live-watch':
            s.add_argument('--duration', type=float, default=30)
            s.add_argument('--max-events', type=int, default=100)
            s.add_argument('--events', default='danmaku,gift,super_chat,live_status')
            s.add_argument('--anonymous', action='store_true')
    return p


def capabilities():
    subparsers = next(a for a in parser()._actions if isinstance(a, argparse._SubParsersAction))
    arguments = {c: [{'name': a.dest, 'flags': a.option_strings, 'required': a.required,
                      'choices': list(a.choices) if a.choices else None, 'default': a.default}
                     for a in subparsers.choices[c]._actions if a.dest != 'help'] for c in COMMANDS}
    return {'version': __version__, 'account_writes': True, 'login_included': True,
            'commands': [{'name': c, 'effect': 'account_write' if c in WRITES else ('authentication' if c == 'login' else ('local' if c in {'capabilities', 'doctor'} else 'read')),
                          'arguments': arguments[c], 'auth_required': c in ACCOUNT or c in WRITES, 'auth_exemption': 'dry_run' if c in WRITES else None, 'output': 'jsonl' if c in {'login', 'live-watch'} else 'json',
                          'validation': 'offline_only_not_live_verified' if c in WRITES or c in (NEW_READS - DM_READS) else 'live_sample_passed' if c in DM_READS or c in {'search','user','user-videos','user-dynamics'} else ('offline' if c in {'capabilities', 'doctor'} else 'underlying_read_route_previously_tested')}
                         for c in COMMANDS],
            'exit_codes': {'0': 'success', '1': 'failure', '2': 'partial or unverified', '130': 'interrupted'},
            'sdk_methods': ['search','user','user_videos','user_dynamics','video','related','subtitles','comments','replies','post_comment','like_video','like_comment','like_dynamic','favorite_video','repost_dynamic', *[c.replace('-','_') for c in sorted(NEW_READS | NEW_WRITES)]],
            'implementation_guide': str(Path(sys.prefix)/'share/bili-agent/docs/IMPLEMENTATION.md'),
            'sdk_source': str(Path(__file__).with_name('sdk.py')),
            'limits': ['No automatic refresh, collection resume or live replay. Writes have no automatic retry; timeout outcomes are unknown.',
                       'complete=false means partial data, including server count mismatches.',
                       'Proxy configuration is process-wide; TLS verification stays enabled.',
                       'Live transport tested; business events have only fixture validation.',
                       'SDK pinned to 17.4.2; upstream maintenance ceased; endpoints may change.']}


async def query(args, cred):
    c = args.command
    if c in WRITES:
        from .sdk import Client
        async with Client(credential_file=args.credential_file) as client:
            options = {'dry_run':args.dry_run}
            if c == 'dm-send':
                return await client.dm_send(args.uid,args.text,**options)
            if c == 'live-send':
                return await client.live_send(args.room,args.text,reply_uid=args.reply_uid,**options)
            if c == 'video-send-danmaku':
                return await client.video_send_danmaku(args.video,args.text,time=args.time,part=args.part,color=args.color,mode=args.mode,**options)
            if c in {'follow-user','block-user'}:
                return await getattr(client,c.replace('-','_'))(args.uid,state=args.state=='on',**options)
            if c == 'watch-later-set':
                return await client.watch_later_set(args.video,state=args.state=='on',**options)
            if c == 'coin-video':
                return await client.coin_video(args.video,count=args.count,like=args.like,**options)
            if c == 'post-dynamic':
                return await client.post_dynamic(args.text,**options)
            if c == 'post-comment':
                return await client.post_comment(args.video,args.text,root=args.root,parent=args.parent,**options)
            if c == 'like-video':
                return await client.like_video(args.video,state=args.state=='on',**options)
            if c == 'like-comment':
                return await client.like_comment(args.video,args.rpid,state=args.state=='on',**options)
            if c == 'like-dynamic':
                return await client.like_dynamic(args.dynamic_id,state=args.state=='on',**options)
            if c == 'favorite-video':
                return await client.favorite_video(args.video,add=args.add,remove=args.remove,**options)
            return await client.repost_dynamic(args.dynamic_id,args.text,**options)
    if c in NEW_READS:
        from .sdk import Client
        async with Client(credential=cred) as client:
            if c == 'dm-sessions':
                return await client.dm_sessions(size=args.size,kind=args.kind,before_ts=args.before_ts)
            if c == 'dm-history':
                return await client.dm_history(args.uid,size=args.size,after_seq=args.after_seq,before_seq=args.before_seq)
            if c == 'dm-new':
                return await client.dm_new(args.since,size=args.size)
            if c == 'dm-session':
                return await client.dm_session(args.uid)
            if c == 'dynamic':
                return await client.dynamic(args.dynamic_id)
            if c == 'user-relation':
                return await client.user_relation(args.uid)
            if c == 'video-state':
                return await client.video_state(args.video)
            if c == 'video-parts':
                return await client.video_parts(args.video)
            return await client.video_danmaku(args.video,part=args.part,segment=args.segment)
    if c in {'search','user','user-videos','user-dynamics','video','related','subtitles','comments','replies'}:
        from .sdk import Client
        async with Client(credential=cred) as client:
            if c == 'search':
                return await client.search(args.keyword,page=args.page,size=args.size,order=args.order)
            if c == 'user':
                return await client.user(args.uid)
            if c == 'user-videos':
                return await client.user_videos(args.uid,page=args.page,size=args.size,keyword=args.keyword,order=args.order)
            if c == 'user-dynamics':
                return await client.user_dynamics(args.uid,offset=args.offset)
            if c == 'video':
                return await client.video(args.video)
            if c == 'related':
                return await client.related(args.video)
            if c == 'subtitles':
                return await client.subtitles(args.video,part=args.part,language=args.language)
            result = (await client.comments(args.video,page=args.page,sort=args.sort) if c=='comments'
                      else await client.replies(args.video,args.root,page=args.page,size=args.size))
            return {'bvid':bvid(args.video),'scope':'one_page','result':result}
    from bilibili_api import user, video, comment, hot, favorite_list, dynamic, live
    if c in {'status', 'whoami'}:
        me = await user.get_self_info(cred)
        return {'session': 'valid', 'credential_modified': False} if c == 'status' else me
    if c == 'hot':
        return await hot.get_hot_videos(pn=args.page, ps=args.size)
    if c == 'history':
        return await user.get_self_history(page_num=args.page, per_page_item=args.size, credential=cred)
    if c == 'watch-later':
        return await user.get_toview_list(cred)
    if c == 'feed':
        return await dynamic.get_dynamic_page_info(cred, _type=dynamic.DynamicType.ALL, pn=args.page, offset=args.offset or None)
    if c in {'my-dynamics', 'following', 'favorites'}:
        if c == 'favorites' and args.folder:
            return await favorite_list.get_video_favorite_list_content(args.folder, page=args.page, credential=cred)
        me = await user.get_self_info(cred)
        owner = user.User(me['mid'], credential=cred)
        if c == 'my-dynamics':
            return await owner.get_dynamics_new(offset=args.offset)
        if c == 'following':
            return await owner.get_followings(pn=args.page, ps=args.size)
        return await favorite_list.get_video_favorite_list(me['mid'], credential=cred)
    if c == 'live-info':
        from .live_read import room_metadata
        return room_metadata(await live.LiveRoom(args.room, credential=cred).get_room_info())
    ident = bvid(args.video)
    item = video.Video(bvid=ident, credential=cred)
    info = await item.get_info()
    aid = info['aid']
    if c in {'all-comments', 'all-replies'}:
        return await collect(args, aid, ident, cred)
    raise SafeError('invalid_command','Unsupported read command.')


def main():
    p = parser()
    args = p.parse_args()
    if (getattr(args, 'page', 1) < 1 or not 1 <= getattr(args, 'size', 20) <= 20
        or (getattr(args, 'root', 1) is not None and getattr(args, 'root', 1) < 1) or getattr(args, 'room', 1) < 1
        or getattr(args, 'folder', None) == 0 or (getattr(args, 'folder', None) or 1) < 1
        or getattr(args,'uid',1) < 1
        or getattr(args, 'part', 1) < 1 or getattr(args, 'max_pages', 1) < 1
        or getattr(args, 'delay', 1) < .5
        or not 0 < getattr(args, 'duration', 30) <= 3600 or getattr(args, 'max_events', 1) < 0):
        p.error('bounds')
    if args.command == 'live-watch' and not set(args.events.split(',')) <= {'danmaku', 'gift', 'super_chat', 'live_status', 'heartbeat'}:
        p.error('events')
    if args.command == 'login' and not 0 < args.timeout <= 300:
        p.error('timeout')
    try:
        if args.command == 'login':
            from .login import login
            return asyncio.run(login(args))
        if args.output and args.output.resolve() == credential_path(args.credential_file).resolve():
            args.output = None
            raise SafeError('unsafe_output', 'Output must not overwrite the credential file.')
        if args.command == 'capabilities':
            data = capabilities()
        elif args.command == 'doctor':
            try:
                sdk = version('bilibili-api-python')
            except PackageNotFoundError:
                sdk = None
            path = credential_path(args.credential_file)
            data = {'version': __version__, 'python': sys.version.split()[0], 'sdk_version': sdk,
                    'credential_file_exists': path.is_file(), 'session_validated': False}
        else:
            if not getattr(args,'dry_run',False):
                configure_sdk_proxy()
            if args.command in VIDEO:
                bvid(args.video)  # Validate before accessing credentials or network.
            cred = None if args.command in WRITES or getattr(args, 'anonymous', False) else load_credential(
                credential_path(args.credential_file), required=args.command in ACCOUNT)
            if args.command == 'live-watch':
                from .live_read import watch
                return asyncio.run(watch(args, cred))
            timeout = 1800 if args.command in {'all-comments', 'all-replies'} else 50
            data = asyncio.run(asyncio.wait_for(query(args, cred), timeout))
        payload = envelope(args.command, data=data)
        if args.command in WRITES:
            payload['effect'] = 'account_write'
            payload['dry_run'] = args.dry_run
            if args.dry_run:
                payload['route'] = 'local'
        code = 2 if isinstance(data, dict) and data.get('complete') is False else 0
    except KeyboardInterrupt:
        if args.command in WRITES:
            print(json.dumps(envelope(args.command,error={
                'code':'interrupted','retryable':False,
                'outcome':'not_sent' if args.dry_run else 'unknown',
                'message':'Interrupted. Check remote state before retrying a write.'})))
        return 130
    except BrokenPipeError:
        return 0
    except Exception as exc:
        error = safe_error(exc)
        if args.command in WRITES:
            error = dict(error, retryable=False)
            error.setdefault('outcome','not_sent' if args.dry_run or error['code'] in {'invalid_arguments','invalid_video','unsafe_output','proxy_invalid','proxy_bypass_unsupported','credential_missing','credential_incomplete','credential_invalid_file','client_closed'} else 'unknown')
        payload = envelope(args.command, error=error)
        code = 1
    try:
        if args.output and args.command not in {'live-watch', 'login'}:
            if code != 1 or args.command not in {'all-comments', 'all-replies'} or not args.output.exists():
                save_private(args.output, payload)
        if args.summary and payload['ok']:
            value = payload['data']
            payload['data'] = ({k: v for k, v in value.items() if k in {
                'status', 'issues', 'session', 'complete', 'root_count', 'reply_count', 'total_count', 'reported_total_count', 'end_reason', 'issues'}}
                if isinstance(value, dict) else {'count': len(value) if isinstance(value, list) else None})
        print(json.dumps(payload, ensure_ascii=False))
    except BrokenPipeError:
        return 0
    except OSError:
        error = {'code':'output_failed','retryable':False}
        if args.command in WRITES:
            error['outcome'] = ('not_sent' if args.dry_run else
                                'succeeded' if payload['ok'] else payload['error'].get('outcome','unknown'))
            error['message'] = 'Output failed; check outcome before repeating a write.'
        print(json.dumps(envelope(args.command,error=error)))
        return 1
    return code
