import asyncio
import unittest
from types import SimpleNamespace
from bili_agent.live_read import normalize, watch, room_metadata


class FakeClient:
    STATUS_ESTABLISHED = 2

    def __init__(self, room, **kwargs):
        self.handlers = {}
        self.status = 0
        self.disconnected = False

    def on(self, name):
        def register(handler):
            self.handlers[name] = handler
            return handler
        return register

    def get_status(self):
        return self.status

    async def connect(self):
        self.status = 2
        self.handlers['ALL']({'type': 'VERIFICATION_SUCCESSFUL', 'data': None})
        for _ in range(3):
            self.handlers['ALL']({'type': 'DANMU_MSG', 'data': {'info': [[], 'same text', [42, 'test']]}})
        await asyncio.sleep(60)

    async def disconnect(self):
        self.disconnected = True
        self.status = 4


class LiveTests(unittest.IsolatedAsyncioTestCase):
    def args(self, **values):
        defaults = dict(room=1, duration=0.05, max_events=2, events='danmaku', output=None)
        defaults.update(values)
        return SimpleNamespace(**defaults)

    def test_normalization_excludes_raw_secrets(self):
        kind, data = normalize({'type': 'DANMU_MSG:4:0', 'data': {
            'info': [[], 'hello', [42, 'name']], 'token': 'DO_NOT_OUTPUT'}})
        self.assertEqual(kind, 'danmaku')
        self.assertNotIn('token', data)
        self.assertEqual(normalize({'type': 'VIEW', 'data': 0}), ('heartbeat', {'popularity': 0}))
        self.assertIsNone(normalize({'type': 'UNKNOWN', 'data': {'token': 'DO_NOT_OUTPUT'}}))

    def test_nested_room_response_and_missing_metadata(self):
        self.assertEqual(room_metadata({'room_info': {'room_id': 7, 'live_status': 1}, 'token': 'DO_NOT_OUTPUT'}),
                         {'room_id': 7, 'live_status': 1})
        with self.assertRaises(ValueError):
            room_metadata({})

    async def test_event_limit_and_disconnect(self):
        records = []
        client = FakeClient(1)
        code = await watch(self.args(), None, factory=lambda *a, **k: client, sink=records.append)
        self.assertEqual(code, 0)
        self.assertTrue(client.disconnected)
        self.assertEqual(sum(r['event'] == 'danmaku' for r in records), 2)
        self.assertEqual(records[-1]['data']['reason'], 'event_limit')

    async def test_no_verification_is_not_success(self):
        class Unverified(FakeClient):
            async def connect(self):
                await asyncio.sleep(60)
        records = []
        code = await watch(self.args(duration=0.01), None, factory=Unverified, sink=records.append)
        self.assertEqual(code, 2)
        self.assertFalse(records[-1]['ok'])

    async def test_connection_failure_does_not_print_exception_body(self):
        class Failed(FakeClient):
            async def connect(self):
                raise RuntimeError('DO_NOT_OUTPUT')
        records = []
        code = await watch(self.args(), None, factory=Failed, sink=records.append)
        self.assertEqual(code, 1)
        self.assertNotIn('DO_NOT_OUTPUT', str(records))


if __name__ == '__main__':
    unittest.main()
