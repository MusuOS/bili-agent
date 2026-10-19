"""Bounded read-only live event stream, with no automatic replies or raw tokens."""
import asyncio
import contextlib
import json
import os
import time
from datetime import datetime, timezone


def room_metadata(response):
    room = response.get('room_info', response)
    if not isinstance(room, dict) or not room.get('room_id'):
        raise ValueError('Missing live room metadata')
    return {key: room[key] for key in ('room_id', 'short_id', 'uid', 'title', 'live_status',
            'live_time', 'live_start_time', 'area_name', 'parent_area_name') if key in room}


def normalize(event):
    command = str(event.get('type', '')).split(':')[0]
    raw = event.get('data')
    if command == 'VERIFICATION_SUCCESSFUL':
        return 'connected', {}
    if command == 'VIEW':
        return 'heartbeat', {'popularity': raw}
    if not isinstance(raw, dict):
        return None
    data = raw.get('data') or {}
    if command == 'DANMU_MSG':
        info = raw.get('info') or []
        if len(info) < 3 or len(info[2]) < 2:
            raise ValueError('Malformed danmaku event')
        return 'danmaku', {'text': info[1], 'user': {'uid': info[2][0], 'name': info[2][1]}}
    if command == 'SEND_GIFT':
        return 'gift', {key: data[key] for key in ('uid', 'uname', 'giftName', 'num', 'coin_type', 'total_coin', 'tid') if key in data}
    if command == 'SUPER_CHAT_MESSAGE':
        result = {key: data[key] for key in ('id', 'uid', 'message', 'price', 'start_time', 'end_time') if key in data}
        result['name'] = (data.get('user_info') or {}).get('uname')
        return 'super_chat', result
    if command in {'LIVE', 'PREPARING'}:
        return 'live_status', {'live': command == 'LIVE'}
    return None


def envelope(room_id, event, data, ok=True):
    return {'schema_version': 1, 'command': 'live-watch', 'ok': ok, 'route': 'http-websocket',
            'room_id': room_id, 'event': event,
            'received_at': datetime.now(timezone.utc).isoformat(), 'data': data}


async def watch(args, credential, factory=None, sink=None):
    uses_sdk = factory is None
    if factory is None:
        from bilibili_api.live import LiveDanmaku
        factory = LiveDanmaku
    client = factory(args.room, credential=credential, debug=False,
                     max_retry=2, retry_after=2, max_retry_for_credential=1)
    # Upstream exception logs may contain response bodies or authentication details.
    if getattr(client, 'logger', None):
        client.logger.disabled = True
    selected = set(args.events.split(','))
    stop = asyncio.Event()
    verified = False
    delivered = malformed = 0
    connected_count = 0
    reason = 'duration_limit'
    started = time.monotonic()

    def emit(kind, data, ok=True):
        record = envelope(args.room, kind, data, ok)
        if sink:
            sink(record)
        else:
            text = json.dumps(record, ensure_ascii=False)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, 'w') as out:
                    os.fchmod(out.fileno(), 0o600)
                    out.write(text + '\n')
            print(text, flush=True)

    # Synchronous handler preserves source dispatch order and avoids queued callbacks at shutdown.
    @client.on('ALL')
    def on_event(event):
        nonlocal verified, delivered, malformed, reason, connected_count
        if stop.is_set():
            return
        try:
            normalized = normalize(event)
        except (ValueError, TypeError, KeyError, IndexError):
            malformed += 1
            return
        if normalized is None:
            return
        kind, data = normalized
        if kind == 'connected':
            verified = True
            connected_count += 1
            emit(kind, {'connection_number': connected_count})
        elif kind in selected:
            emit(kind, data)
            delivered += 1
            if args.max_events and delivered >= args.max_events:
                reason = 'event_limit'
                stop.set()

    @client.on('TIMEOUT')
    def on_timeout(event):
        emit('connection_warning', {'type': 'heartbeat_timeout'})

    @client.on('__TASK_EXCEPTION__')
    def on_task_error(error):
        nonlocal reason
        reason = 'handler_failed'
        stop.set()

    emit('starting', {'duration_seconds': args.duration, 'max_events': args.max_events,
                      'auth': 'saved_session' if credential else 'anonymous', 'selected_events': sorted(selected)})
    connection = asyncio.create_task(client.connect())
    stopper = asyncio.create_task(stop.wait())
    timer = asyncio.create_task(asyncio.sleep(args.duration))
    code = 0
    try:
        completed, _ = await asyncio.wait([connection, stopper, timer], return_when=asyncio.FIRST_COMPLETED)
        if connection in completed:
            try:
                connection.result()
                reason = 'connection_ended'
                code = 2
            except Exception as exc:
                reason = 'connection_failed'
                code = 1
                emit('error', {'type': type(exc).__name__}, False)
        elif reason == 'handler_failed':
            code = 1
        if not verified and not code:
            reason = 'authentication_not_confirmed'
            code = 2
        elif not code and client.get_status() != client.STATUS_ESTABLISHED:
            reason = 'connection_unavailable_at_limit'
            code = 2
    finally:
        stop.set()
        if client.get_status() == client.STATUS_ESTABLISHED:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(client.disconnect(), timeout=5)
        for task in (connection, stopper, timer):
            task.cancel()
        await asyncio.gather(connection, stopper, timer, return_exceptions=True)
        if uses_sdk:
            from bilibili_api.utils.network import get_client
            with contextlib.suppress(Exception):
                await asyncio.wait_for(get_client().close(), timeout=5)
    emit('finished', {'reason': reason, 'authenticated_connection': verified,
                     'events_received': delivered, 'malformed_events': malformed,
                     'connections': connected_count, 'elapsed_seconds': round(time.monotonic() - started, 2),
                     'history_complete': False}, code == 0)
    return code
