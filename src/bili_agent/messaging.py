"""Private-message primitives for pinned SDK 17.4.2. Never mark a session read."""
import json
import time

from .auth import SafeError


def _api(section, name, credential):
    from bilibili_api.utils.network import Api
    from bilibili_api.utils.utils import get_api
    return Api(**get_api('session')[section][name], credential=credential)


async def sessions(size, kind, before_ts, credential):
    params = {'session_type':kind, 'size':size, 'group_fold':1, 'unfollow_fold':0,
              'sort_rule':2, 'build':0, 'mobi_app':'web'}
    if before_ts is not None:
        params['end_ts'] = before_ts
    return await _api('session','get',credential).update_params(**params).result


async def history(uid, size, after_seq, before_seq, credential):
    params = {'talker_id':uid, 'session_type':1, 'size':size, 'build':0, 'mobi_app':'web'}
    # Omission differs from 0: no cursor asks for the current page; 0 starts at the beginning.
    if after_seq is not None:
        params['begin_seqno'] = after_seq
    if before_seq is not None:
        params['end_seqno'] = before_seq
    return await _api('session','fetch',credential).update_params(**params).result


async def new(since, size, credential):
    # Always explicit; upstream's default timestamp is evaluated at import time.
    return await _api('session','new',credential).update_params(
        begin_ts=since, size=size, build=0, mobi_app='web').result


async def detail(uid, credential):
    return await _api('session','get_session_detail',credential).update_params(
        talker_id=uid, session_type=1).result


async def send(uid, text, credential):
    from bilibili_api.user import get_self_info
    me = await get_self_info(credential)
    sender = me.get('mid') if isinstance(me,dict) else None
    if not isinstance(sender,int) or isinstance(sender,bool) or sender < 1:
        raise SafeError('response_invalid','Sender identity was missing from response.')
    data = {'msg[sender_uid]':sender, 'msg[receiver_id]':uid, 'msg[receiver_type]':1,
            'msg[msg_type]':1, 'msg[msg_status]':0,
            'msg[content]':json.dumps({'content':text},ensure_ascii=False),
            # Public SDK device identifier, not a credential or an idempotency key.
            'msg[dev_id]':'A6716E9A-7CE3-47AF-994B-F0B34178D28D',
            'msg[new_face_version]':0, 'msg[timestamp]':int(time.time()),
            'from_filework':0, 'build':0, 'mobi_app':'web'}
    api = _api('operate','send_msg',credential).update_params(
        w_sender_uid=sender,w_receiver_id=uid).update_data(**data)
    # Api.result/request retry a WBI -403; _request performs one attempt, including signing.
    # This private entry point is intentionally tied to the pinned 17.4.2 SDK and tested.
    return await api._request()
