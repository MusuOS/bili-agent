import unittest
from bili_agent.collect import pages, verify_collection


def response(number, ids, count=2, **extra):
    return {'page': {'num': number, 'size': 20, 'count': count},
            'replies': [{'rpid': ident} for ident in ids], **extra}


class PaginationTests(unittest.IsolatedAsyncioTestCase):
    async def run_pages(self, responses, **kwargs):
        async def fetch(number):
            item = responses[number - 1]
            if isinstance(item, Exception):
                raise item
            return item
        return await pages(fetch, len(responses), 0, **kwargs)

    async def test_pinned_duplicate_and_empty_terminal(self):
        result = await self.run_pages([
            response(1, [1, 2], upper={'top': {'rpid': 2}}),
            response(2, [], upper={'top': {'rpid': 2}})], include_pinned=True)
        self.assertTrue(result['complete'])
        self.assertEqual([r['rpid'] for r in result['comments']], [1, 2])

    async def test_short_page_is_not_terminal(self):
        result = await self.run_pages([response(1, [1]), response(2, [2]), response(3, [])])
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['pages']), 3)

    async def test_repeated_page_is_incomplete(self):
        result = await self.run_pages([response(1, [1, 2]), response(2, [1, 2])])
        self.assertFalse(result['complete'])
        self.assertEqual(result['end_reason'], 'repeated_page')

    async def test_failure_preserves_collected_rows(self):
        result = await self.run_pages([response(1, [1]), TimeoutError()])
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['comments']), 1)
        self.assertEqual(result['end_reason'], 'request_failed')

    async def test_hidden_or_changing_count_is_incomplete(self):
        for responses in ([response(1, [1]), response(2, [])],
                          [response(1, [1], count=1), response(2, [], count=2)]):
            result = await self.run_pages(responses)
            self.assertFalse(result['complete'])

    async def test_page_limit_is_incomplete(self):
        result = await self.run_pages([response(1, [1, 2])])
        self.assertFalse(result['complete'])
        self.assertEqual(result['end_reason'], 'page_limit')

    async def test_root_count_includes_replies(self):
        root_pages = await self.run_pages([response(1, [1], count=2), response(2, [], count=2)],
                                         compare_count=False)
        self.assertTrue(root_pages['complete'])
        root_pages.pop('comments')
        result = verify_collection({'root_pagination': root_pages, 'issues': [],
            'comments': [{'rpid': 1, 'replies_complete': True, 'replies': [{'rpid': 2}]}]})
        self.assertTrue(result['complete'])
        self.assertEqual(result['total_count'], 2)

    async def test_duplicate_reply_ids_cannot_be_complete(self):
        result = verify_collection({'root_pagination': {'end_reason': 'empty_page', 'issues': [],
            'pages': [{'reported_count': 2}]}, 'issues': [],
            'comments': [{'rpid': 1, 'replies_complete': True, 'replies': [{'rpid': 1}]}]})
        self.assertFalse(result['complete'])
        self.assertIn({'type': 'duplicate_ids'}, result['issues'])


if __name__ == '__main__':
    unittest.main()
