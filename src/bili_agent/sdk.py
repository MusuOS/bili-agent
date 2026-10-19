"""Small async primitive API. Return upstream business data; do not compose products."""
import asyncio
import math
import re
from urllib.parse import urlparse

from .auth import SafeError, credential_path, load_credential
from .errors import AgentError, safe_error
from .identifiers import bvid
from .network import configure_sdk_proxy, selected_proxy

_UNSET = object()


def positive(value, name):
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise AgentError({'code':'invalid_arguments','message':f'{name} must be a positive integer.','retryable':False})
    return value


def pagination(page, size):
    positive(page, 'page')
    positive(size, 'size')
    if size > 20:
        raise AgentError({'code':'invalid_arguments','message':'size must be at most 20.','retryable':False})


class BilibiliTransport:
    """Only this layer knows upstream definitions and enum names."""
    async def search(self, keyword, page, size, order, credential):
        from bilibili_api.utils.network import Api
        from bilibili_api.utils.utils import get_api
        definition = get_api('search')['search']['web_search_by_type']
        return await Api(**definition, wbi=True, credential=credential).update_params(
            keyword=keyword, page=page, page_size=size, search_type='video', order=order).result

    async def user(self, uid, credential):
        from bilibili_api.user import User
        return await User(uid, credential=credential).get_user_info()

    async def user_videos(self, uid, page, size, keyword, order, credential):
        from bilibili_api.user import User, VideoOrder
        return await User(uid, credential=credential).get_videos(pn=page, ps=size, keyword=keyword, order=VideoOrder(order))

    async def user_dynamics(self, uid, offset, credential):
        from bilibili_api.user import User
        return await User(uid, credential=credential).get_dynamics_new(offset=offset)

    async def video(self, ident, credential):
        from bilibili_api.video import Video
        return await Video(bvid=ident, credential=credential).get_info()

    async def related(self, ident, credential):
        from bilibili_api.video import Video
        return await Video(bvid=ident, credential=credential).get_related()

    async def subtitles(self, ident, part, language, credential):
        from bilibili_api.video import Video
        item = Video(bvid=ident, credential=credential)
        parts = await item.get_pages()
        if part > len(parts):
            raise SafeError('part_not_found', 'Video part does not exist.')
        tracks = await item.get_subtitle(cid=parts[part-1]['cid']) or {'subtitles': []}
        if language is None:
            return tracks
        selected = next((track for track in tracks.get('subtitles', []) if track.get('lan') == language), None)
        if not selected:
            raise SafeError('subtitle_not_found', 'Selected subtitle language is unavailable.')
        url = selected.get('subtitle_url', '')
        if url.startswith('//'):
            url = 'https:' + url
        parsed = urlparse(url)
        if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.hdslb.com'):
            raise SafeError('subtitle_host_rejected', 'Unsupported subtitle CDN.')
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),trust_env=False) as session:
            async with session.get(url, allow_redirects=False, proxy=selected_proxy()) as response:
                response.raise_for_status()
                data = await response.json()
        if not isinstance(data.get('body'), list):
            raise SafeError('response_invalid', 'Subtitle body was missing.')
        return {'bvid':ident, 'language':language, 'subtitle':data}

    async def comments(self, aid, page, sort, credential):
        from bilibili_api import comment
        return await comment.get_comments(aid, comment.CommentResourceType.VIDEO, page_index=page,
            order=comment.OrderType.LIKE if sort=='like' else comment.OrderType.TIME, credential=credential)

    async def replies(self, aid, root, page, size, credential):
        from bilibili_api import comment
        return await comment.Comment(aid, comment.CommentResourceType.VIDEO, root,
            credential=credential).get_sub_comments(page_index=page, page_size=size)


    async def post_comment(self, aid, text, root, parent, credential):
        from bilibili_api import comment
        return await comment.send_comment(text, aid, comment.CommentResourceType.VIDEO,
                                          root=root, parent=parent, credential=credential)

    async def like_video(self, ident, state, credential):
        from bilibili_api.video import Video
        return await Video(bvid=ident, credential=credential).like(state)

    async def like_comment(self, aid, rpid, state, credential):
        from bilibili_api import comment
        return await comment.Comment(aid, comment.CommentResourceType.VIDEO, rpid,
                                     credential=credential).like(state)

    async def like_dynamic(self, dynamic_id, state, credential):
        from bilibili_api.dynamic import Dynamic
        return await Dynamic(dynamic_id, credential=credential).set_like(state)

    async def favorite_video(self, ident, add, remove, credential):
        from bilibili_api.video import Video
        return await Video(bvid=ident, credential=credential).set_favorite(
            add_media_ids=add, del_media_ids=remove)

    async def repost_dynamic(self, dynamic_id, text, credential):
        from bilibili_api.dynamic import Dynamic
        return await Dynamic(dynamic_id, credential=credential).repost(text=text)


    async def dynamic(self, dynamic_id, credential):
        from bilibili_api.dynamic import Dynamic
        return await Dynamic(dynamic_id, credential=credential).get_info()

    async def user_relation(self, uid, credential):
        from bilibili_api.user import User
        return await User(uid, credential=credential).get_relation()

    async def video_parts(self, ident, credential):
        from bilibili_api.video import Video
        return await Video(bvid=ident, credential=credential).get_pages()

    async def video_state(self, ident, credential):
        from bilibili_api.video import Video
        item = Video(bvid=ident, credential=credential)
        return {'liked':bool(await item.has_liked()), 'favoured':bool(await item.has_favoured()),
                'coins':await item.get_pay_coins()}

    async def video_danmaku(self, ident, part, segment, credential):
        from bilibili_api.video import Video
        items = await Video(bvid=ident, credential=credential).get_danmakus(
            page_index=part-1, from_seg=segment-1, to_seg=segment-1)
        fields = {'id':'id_', 'id_str':'id_str', 'text':'text', 'time':'dm_time',
                  'color':'color', 'mode':'mode', 'font_size':'font_size', 'send_time':'send_time'}
        return {'bvid':ident, 'part':part, 'segment':segment, 'scope':'one_segment',
                'items':[{key:getattr(item,attr,None) for key,attr in fields.items()} for item in items]}

    async def live_send(self, room, text, reply_uid, credential):
        from bilibili_api.live import LiveRoom
        from bilibili_api.utils.danmaku import Danmaku
        # Let the SDK resolve short room IDs to the real room ID.
        return await LiveRoom(room, credential=credential).send_danmaku(
            Danmaku(text=text), reply_mid=reply_uid)

    async def video_send_danmaku(self, ident, text, time, part, color, mode, credential):
        from bilibili_api.video import Video
        from bilibili_api.utils.danmaku import Danmaku
        return await Video(bvid=ident, credential=credential).send_danmaku(
            page_index=part-1, danmaku=Danmaku(text=text, dm_time=time, color=color, mode=mode))

    async def follow_user(self, uid, state, credential):
        from bilibili_api.user import User, RelationType
        return await User(uid, credential=credential).modify_relation(
            RelationType.SUBSCRIBE if state else RelationType.UNSUBSCRIBE)

    async def block_user(self, uid, state, credential):
        from bilibili_api.user import User, RelationType
        return await User(uid, credential=credential).modify_relation(
            RelationType.BLOCK if state else RelationType.UNBLOCK)

    async def watch_later_set(self, ident, state, credential):
        from bilibili_api.video import Video
        item = Video(bvid=ident, credential=credential)
        return await (item.add_to_toview() if state else item.delete_from_toview())

    async def coin_video(self, ident, count, like, credential):
        from bilibili_api.video import Video
        return await Video(bvid=ident, credential=credential).pay_coin(num=count, like=like)

    async def post_dynamic(self, text, credential):
        from bilibili_api.dynamic import BuildDynamic, send_dynamic
        # Plain text intentionally preserves @ and bracketed strings as text.
        return await send_dynamic(BuildDynamic.empty().add_plain_text(text), credential=credential)


    async def dm_sessions(self, size, kind, before_ts, credential):
        from .messaging import sessions
        return await sessions(size,kind,before_ts,credential)

    async def dm_history(self, uid, size, after_seq, before_seq, credential):
        from .messaging import history
        return await history(uid,size,after_seq,before_seq,credential)

    async def dm_new(self, since, size, credential):
        from .messaging import new
        return await new(since,size,credential)

    async def dm_session(self, uid, credential):
        from .messaging import detail
        return await detail(uid,credential)

    async def dm_send(self, uid, text, credential):
        from .messaging import send
        return await send(uid,text,credential)


class Client:
    """Async primitive reads and writes; one Client per event loop.

    Credential file is loaded lazily. Explicit credential=None selects anonymous reads.
    Returns upstream data without CLI envelopes; dry_run returns an offline operation plan.
    Errors are redacted AgentError objects; uncertain writes must not be blindly retried.
    Upstream SDK sessions are shared per loop; close after all clients finish using them.
    """
    def __init__(self, credential_file=None, *, credential=_UNSET, transport=None, timeout=45):
        if not 0 < timeout <= 120:
            raise ValueError('timeout must be in (0, 120]')
        self.credential_file = credential_file
        self.credential = credential
        self.transport = transport or BilibiliTransport()
        self.timeout = timeout
        self._owns_transport = transport is None
        self._closed = False
        self._used = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    async def aclose(self):
        if self._closed:
            return
        self._closed = True
        if self._owns_transport and self._used:
            from bilibili_api.utils.network import get_client
            await asyncio.wait_for(get_client().close(), 5)

    def _credential(self):
        if self.credential is _UNSET:
            self.credential = load_credential(credential_path(self.credential_file))
        return self.credential

    async def _call(self, name, *args):
        if self._closed:
            raise AgentError({'code':'client_closed','message':'Client is closed.','retryable':False})
        try:
            if self._owns_transport:
                configure_sdk_proxy()
            credential = self._credential()
            self._used = True
            return await asyncio.wait_for(getattr(self.transport, name)(*args, credential), self.timeout)
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError(safe_error(exc)) from None

    def _bvid(self, value):
        try:
            return bvid(value)
        except SafeError as exc:
            raise AgentError(safe_error(exc)) from None

    async def search(self, keyword, *, page=1, size=20, order='totalrank'):
        """One page of video search; result/numResults/numPages are upstream fields."""
        pagination(page, size)
        if not isinstance(keyword,str) or not keyword.strip() or order not in {'totalrank','click','pubdate','dm','stow'}:
            raise AgentError({'code':'invalid_arguments','message':'Invalid search parameters.','retryable':False})
        return await self._call('search',keyword.strip(),page,size,order)

    async def user(self, uid):
        """Public user profile by numeric UID."""
        return await self._call('user',positive(uid,'uid'))

    async def user_videos(self, uid, *, page=1, size=20, keyword='', order='pubdate'):
        """One page of uploads; list.vlist and page are upstream fields."""
        positive(uid,'uid')
        pagination(page,size)
        if not isinstance(keyword,str) or order not in {'pubdate','click','stow'}:
            raise AgentError({'code':'invalid_arguments','message':'Invalid upload-list parameters.','retryable':False})
        return await self._call('user_videos',uid,page,size,keyword,order)

    async def user_dynamics(self, uid, *, offset=''):
        """One page of user dynamics; pass the returned offset to the next call."""
        positive(uid,'uid')
        if not isinstance(offset,str):
            raise AgentError({'code':'invalid_arguments','message':'offset must be a string.','retryable':False})
        return await self._call('user_dynamics',uid,offset)

    async def video(self, video):
        return await self._call('video',self._bvid(video))

    async def related(self, video):
        return await self._call('related',self._bvid(video))

    async def subtitles(self, video, *, part=1, language=None):
        """List tracks by default; language selects one raw timed subtitle body."""
        positive(part,'part')
        if language is not None and (not isinstance(language,str) or not language.strip()):
            raise AgentError({'code':'invalid_arguments','message':'Invalid subtitle language.','retryable':False})
        return await self._call('subtitles',self._bvid(video),part,language)

    async def _aid(self, ident):
        info = await self.video(ident)
        aid = info.get('aid') if isinstance(info,dict) else None
        if not isinstance(aid,int) or isinstance(aid,bool) or aid < 1:
            raise AgentError({'code':'response_invalid','message':'Video identifier was missing from response.','retryable':False})
        return aid

    async def comments(self, video, *, page=1, sort='like'):
        positive(page,'page')
        if sort not in {'like','time'}:
            raise AgentError({'code':'invalid_arguments','message':'Invalid comment order.','retryable':False})
        ident = self._bvid(video)
        aid = await self._aid(ident)
        return await self._call('comments',aid,page,sort)

    async def replies(self, video, root, *, page=1, size=20):
        positive(root,'root')
        pagination(page,size)
        ident = self._bvid(video)
        aid = await self._aid(ident)
        return await self._call('replies',aid,root,page,size)


    async def _write(self, name, args, parameters, dry_run, *, resolve_video=False):
        if not isinstance(dry_run, bool):
            raise AgentError({'code':'invalid_arguments','message':'dry_run must be a boolean.','retryable':False})
        if self._closed:
            raise AgentError({'code':'client_closed','message':'Client is closed.','retryable':False})
        if dry_run:
            return {'dry_run':True,'request_sent':False,'effect':'account_write',
                    'operation':name,'parameters':parameters}
        dispatched = False
        try:
            if self._owns_transport:
                configure_sdk_proxy()
            credential = self._credential()
            if credential is None or not credential.has_sessdata():
                raise SafeError('credential_missing','Run bili-agent login before account writes.')
            if not credential.has_bili_jct():
                raise SafeError('credential_incomplete','Saved session lacks CSRF data; log in again.')
            if resolve_video:
                args = (await self._aid(args[0]), *args[1:])
            self._used = True
            dispatched = True
            return await asyncio.wait_for(getattr(self.transport, name)(*args, credential), self.timeout)
        except Exception as exc:
            error = dict(safe_error(exc))
            error['retryable'] = False
            # Once dispatched, conservatively assume the mutation may have reached Bilibili.
            error['outcome'] = 'unknown' if dispatched else 'not_sent'
            if dispatched:
                error['message'] = 'Write result is uncertain. Check remote state before retrying.'
            raise AgentError(error) from None

    def _state(self, state):
        if not isinstance(state, bool):
            raise AgentError({'code':'invalid_arguments','message':'state must be a boolean.','retryable':False})
        return state

    def _text(self, text):
        if not isinstance(text, str) or not text.strip():
            raise AgentError({'code':'invalid_arguments','message':'Text must be a nonempty string.','retryable':False})
        return text

    async def post_comment(self, video, text, *, root=None, parent=None, dry_run=False):
        """Post a text comment or reply on a video. No images or automatic retry."""
        ident = self._bvid(video)
        self._text(text)
        if root is not None:
            positive(root,'root')
        if parent is not None:
            positive(parent,'parent')
            if root is None:
                raise AgentError({'code':'invalid_arguments','message':'parent requires root.','retryable':False})
        return await self._write('post_comment',(ident,text,root,parent),
            {'video':ident,'text':text,'root':root,'parent':parent},dry_run,resolve_video=True)

    async def like_video(self, video, *, state=True, dry_run=False):
        ident = self._bvid(video)
        self._state(state)
        return await self._write('like_video',(ident,state),{'video':ident,'state':state},dry_run)

    async def like_comment(self, video, rpid, *, state=True, dry_run=False):
        ident = self._bvid(video)
        positive(rpid,'rpid')
        self._state(state)
        return await self._write('like_comment',(ident,rpid,state),
            {'video':ident,'rpid':rpid,'state':state},dry_run,resolve_video=True)

    async def like_dynamic(self, dynamic_id, *, state=True, dry_run=False):
        positive(dynamic_id,'dynamic_id')
        self._state(state)
        return await self._write('like_dynamic',(dynamic_id,state),
            {'dynamic_id':dynamic_id,'state':state},dry_run)

    async def favorite_video(self, video, *, add=(), remove=(), dry_run=False):
        ident = self._bvid(video)
        if not isinstance(add,(tuple,list)) or not isinstance(remove,(tuple,list)):
            raise AgentError({'code':'invalid_arguments','message':'Folders must be lists of IDs.','retryable':False})
        for folder in (*add,*remove):
            positive(folder,'folder')
        add, remove = list(dict.fromkeys(add)), list(dict.fromkeys(remove))
        if (not add and not remove) or set(add) & set(remove):
            raise AgentError({'code':'invalid_arguments','message':'Provide distinct folders to add or remove.','retryable':False})
        return await self._write('favorite_video',(ident,add,remove),
            {'video':ident,'add':add,'remove':remove},dry_run)

    async def repost_dynamic(self, dynamic_id, text='转发动态', *, dry_run=False):
        positive(dynamic_id,'dynamic_id')
        self._text(text)
        return await self._write('repost_dynamic',(dynamic_id,text),
            {'dynamic_id':dynamic_id,'text':text},dry_run)


    async def dynamic(self, dynamic_id):
        return await self._call('dynamic',positive(dynamic_id,'dynamic_id'))

    async def video_parts(self, video):
        return await self._call('video_parts',self._bvid(video))

    async def _account_read(self, name, *args):
        if self._closed:
            raise AgentError({'code':'client_closed','message':'Client is closed.','retryable':False})
        try:
            if self._owns_transport:
                configure_sdk_proxy()
            credential = self._credential()
            if credential is None or not credential.has_sessdata():
                raise SafeError('credential_missing','Run bili-agent login before account reads.')
        except Exception as exc:
            raise AgentError(safe_error(exc)) from None
        return await self._call(name,*args)

    async def user_relation(self, uid):
        return await self._account_read('user_relation',positive(uid,'uid'))

    async def video_state(self, video):
        return await self._account_read('video_state',self._bvid(video))

    async def video_danmaku(self, video, *, part=1, segment=1):
        positive(part,'part')
        positive(segment,'segment')
        return await self._call('video_danmaku',self._bvid(video),part,segment)

    async def live_send(self, room, text, *, reply_uid=None, dry_run=False):
        positive(room,'room')
        self._text(text)
        if reply_uid is not None:
            positive(reply_uid,'reply_uid')
        return await self._write('live_send',(room,text,reply_uid),
            {'room':room,'text':text,'reply_uid':reply_uid},dry_run)

    async def video_send_danmaku(self, video, text, *, time=0, part=1, color='ffffff', mode=1, dry_run=False):
        ident = self._bvid(video)
        self._text(text)
        positive(part,'part')
        if (isinstance(time,bool) or not isinstance(time,(int,float)) or not math.isfinite(time) or time < 0
            or not isinstance(color,str) or not re.fullmatch(r'[0-9a-fA-F]{6}',color)
            or isinstance(mode,bool) or not isinstance(mode,int) or mode not in {1,4,5}):
            raise AgentError({'code':'invalid_arguments','message':'Invalid danmaku time, color or mode.','retryable':False})
        color = color.lower()
        return await self._write('video_send_danmaku',(ident,text,time,part,color,mode),
            {'video':ident,'text':text,'time':time,'part':part,'color':color,'mode':mode},dry_run)

    async def follow_user(self, uid, *, state=True, dry_run=False):
        positive(uid,'uid')
        self._state(state)
        return await self._write('follow_user',(uid,state),{'uid':uid,'state':state},dry_run)

    async def block_user(self, uid, *, state=True, dry_run=False):
        positive(uid,'uid')
        self._state(state)
        return await self._write('block_user',(uid,state),{'uid':uid,'state':state},dry_run)

    async def watch_later_set(self, video, *, state=True, dry_run=False):
        ident = self._bvid(video)
        self._state(state)
        return await self._write('watch_later_set',(ident,state),{'video':ident,'state':state},dry_run)

    async def coin_video(self, video, *, count=1, like=False, dry_run=False):
        ident = self._bvid(video)
        positive(count,'count')
        self._state(like)
        if count > 2:
            raise AgentError({'code':'invalid_arguments','message':'Coin count must be 1 or 2.','retryable':False})
        return await self._write('coin_video',(ident,count,like),{'video':ident,'count':count,'like':like},dry_run)

    async def post_dynamic(self, text, *, dry_run=False):
        self._text(text)
        return await self._write('post_dynamic',(text,),{'text':text},dry_run)


    def _dm_size(self, size):
        pagination(1,size)

    def _dm_cursor(self, value, name, *, optional=False):
        if optional and value is None:
            return
        if not isinstance(value,int) or isinstance(value,bool) or value < 0:
            raise AgentError({'code':'invalid_arguments','message':f'{name} must be a nonnegative integer.','retryable':False})

    async def dm_sessions(self, *, size=20, kind=1, before_ts=None):
        """One page of account sessions. before_ts is a microsecond end timestamp."""
        self._dm_size(size)
        positive(kind,'kind')
        if kind > 9:
            raise AgentError({'code':'invalid_arguments','message':'Session kind must be 1 through 9.','retryable':False})
        self._dm_cursor(before_ts,'before_ts',optional=True)
        return await self._account_read('dm_sessions',size,kind,before_ts)

    async def dm_history(self, uid, *, size=20, after_seq=None, before_seq=None):
        """One user-message page. after_seq and before_seq are exclusive sequence cursors."""
        positive(uid,'uid')
        self._dm_size(size)
        self._dm_cursor(after_seq,'after_seq',optional=True)
        self._dm_cursor(before_seq,'before_seq',optional=True)
        if after_seq is not None and before_seq is not None:
            raise AgentError({'code':'invalid_arguments','message':'Choose after_seq or before_seq, not both.','retryable':False})
        return await self._account_read('dm_history',uid,size,after_seq,before_seq)

    async def dm_new(self, since, *, size=20):
        """Changed sessions since a microsecond timestamp; fetch each session's messages separately."""
        self._dm_cursor(since,'since')
        self._dm_size(size)
        return await self._account_read('dm_new',since,size)

    async def dm_session(self, uid):
        return await self._account_read('dm_session',positive(uid,'uid'))

    async def dm_send(self, uid, text, *, dry_run=False):
        """Send a single plain-text user message, without automatic retries."""
        positive(uid,'uid')
        self._text(text)
        return await self._write('dm_send',(uid,text),{'uid':uid,'text':text},dry_run)
