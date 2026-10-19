"""Bounded sequential collection with explicit termination and partial results."""
import asyncio
import copy
import json
import os
import tempfile
from pathlib import Path


def save_private(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(payload, out, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


async def pages(fetch, max_pages, delay, progress=None, include_pinned=False, compare_count=True):
    rows, metadata, issues, seen_pages = {}, [], [], set()
    result = {'complete': False, 'end_reason': 'page_limit', 'pages': metadata,
              'issues': issues, 'comments': []}
    for number in range(1, max_pages + 1):
        try:
            if number > 1:
                await asyncio.sleep(delay)
            data = await asyncio.wait_for(fetch(number), timeout=30)
            page = data['page']
            if int(page['num']) != number or int(page['size']) < 1:
                raise ValueError('Unexpected page metadata')
            batch = data.get('replies') or []
            if not isinstance(batch, list):
                raise ValueError('Unexpected comments')
            ids = tuple(str(row['rpid']) for row in batch)
            metadata.append({'number': number, 'size': page['size'],
                             'reported_count': page['count'], 'returned': len(batch)})
            extra = []
            if include_pinned:
                extra.extend(data.get('top_replies') or [])
                top = data.get('upper', {}).get('top')
                if isinstance(top, dict):
                    extra.append(top)
                extra.extend(v for v in (data.get('top') or {}).values() if isinstance(v, dict) and v.get('rpid'))
            for row in batch + extra:
                rows[str(row['rpid'])] = copy.deepcopy(row)
            result['comments'] = list(rows.values())
            if not batch:
                result['end_reason'] = 'empty_page'
                result['complete'] = True
            elif ids in seen_pages:
                issues.append({'type': 'repeated_page', 'page': number})
                result['end_reason'] = 'repeated_page'
            else:
                seen_pages.add(ids)
            if progress:
                progress(result)
            if result['end_reason'] != 'page_limit':
                break
        except Exception as exc:
            issues.append({'type': type(exc).__name__, 'page': number})
            result['end_reason'] = 'request_failed'
            break
    if metadata and len({p['reported_count'] for p in metadata}) > 1:
        issues.append({'type': 'count_changed'})
        result['complete'] = False
    if compare_count and result['complete'] and metadata and len(rows) < int(metadata[-1]['reported_count']):
        issues.append({'type': 'visible_count_below_reported', 'reported': metadata[-1]['reported_count'], 'visible': len(rows)})
        result['complete'] = False
    return result


def verify_collection(result):
    """Recheck retained rows and endpoint counts without making network requests."""
    roots = result['comments']
    root_page = result['root_pagination']
    # The root endpoint's count includes replies, so compare it with total rows below.
    root_page['issues'] = [item for item in root_page['issues']
                           if item['type'] != 'visible_count_below_reported']
    root_page['complete'] = root_page['end_reason'] == 'empty_page' and not root_page['issues']
    result['root_count'] = len(roots)
    result['reply_count'] = sum(len(row.get('replies') or []) for row in roots)
    result['total_count'] = result['root_count'] + result['reply_count']
    ids = [str(row['rpid']) for row in roots]
    ids.extend(str(reply['rpid']) for row in roots for reply in row.get('replies') or [])
    issues = [item for item in result['issues'] if item['type'] not in {'duplicate_ids', 'total_count_below_reported'}]
    if len(ids) != len(set(ids)):
        issues.append({'type': 'duplicate_ids'})
    for row in roots:
        for reply in row.get('replies') or []:
            if reply.get('root') is not None and str(reply['root']) != str(row['rpid']):
                issues.append({'type': 'reply_root_mismatch', 'root_id': row['rpid']})
                break
    if root_page['pages']:
        result['reported_total_count'] = int(root_page['pages'][-1]['reported_count'])
        result['declared_reply_count'] = sum(int(row.get('rcount') or 0) for row in roots)
        if result['total_count'] < result['reported_total_count']:
            issues.append({'type': 'total_count_below_reported',
                           'reported': result['reported_total_count'], 'visible': result['total_count']})
    result['issues'] = issues
    result['complete'] = root_page['complete'] and not issues and all(
        row.get('replies_complete', False) for row in roots)
    return result


async def collect(args, aid, bvid, credential):
    from bilibili_api import comment
    resource = comment.CommentResourceType.VIDEO
    result = {'bvid': bvid, 'aid': aid, 'scope': 'all_visible', 'complete': False,
              'root_count': 0, 'reply_count': 0, 'comments': [], 'issues': []}

    def checkpoint():
        result['root_count'] = len(result['comments'])
        result['reply_count'] = sum(len(row.get('replies') or []) for row in result['comments'])
        result['total_count'] = result['root_count'] + result['reply_count']
        if args.output:
            save_private(args.output, {'schema_version': 1, 'command': args.command, 'ok': True, 'route': 'pure-http', 'data': result})

    if args.command == 'all-replies':
        item = comment.Comment(aid, resource, args.root, credential=credential)
        fetched = await pages(lambda page: item.get_sub_comments(page_index=page, page_size=20),
                              args.max_pages, args.delay)
        return {'bvid': bvid, 'root_id': args.root, 'scope': 'all_visible_replies',
                'reply_count': len(fetched['comments']), **fetched}

    def root_progress(state):
        result['comments'] = state['comments']
        result['root_pagination'] = {k: v for k, v in state.items() if k != 'comments'}
        # Preview replies are retained but never counted as completed threads.
        for row in result['comments']:
            row['replies_complete'] = False
        checkpoint()

    roots = await pages(lambda page: comment.get_comments(aid, resource, page_index=page,
                        order=comment.OrderType.TIME, credential=credential),
                        args.max_pages, args.delay, root_progress, include_pinned=True, compare_count=False)
    result['root_pagination'] = {k: v for k, v in roots.items() if k != 'comments'}
    result['comments'] = roots['comments']
    if roots['end_reason'] == 'request_failed':
        result['issues'].append({'type': 'stopped_after_request_failure'})
        checkpoint()
        return result
    for index, row in enumerate(result['comments']):
        expected = int(row.get('rcount') or 0)
        if expected == 0 and not row.get('replies'):
            row['replies_complete'] = True
            continue
        await asyncio.sleep(args.delay)
        item = comment.Comment(aid, resource, row['rpid'], credential=credential)
        replies = await pages(lambda page: item.get_sub_comments(page_index=page, page_size=20),
                              args.max_pages, args.delay)
        # Full endpoint result replaces previews, which may contain stale/deleted IDs.
        row['replies'] = replies.pop('comments')
        row['reply_pagination'] = replies
        row['replies_complete'] = replies['complete'] and len(row['replies']) >= expected
        if len(row['replies']) != expected:
            result['issues'].append({'type': 'reply_count_changed_or_hidden', 'root_id': row['rpid'],
                                     'expected': expected, 'visible': len(row['replies'])})
        checkpoint()
        if replies['end_reason'] == 'request_failed':
            result['issues'].append({'type': 'stopped_after_request_failure'})
            break
    verify_collection(result)
    checkpoint()
    return result
