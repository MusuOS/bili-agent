import re
from urllib.parse import urlparse
from .auth import SafeError


def bvid(value):
    if re.fullmatch(r'BV[0-9A-Za-z]{10}', value):
        return value
    u = urlparse(value)
    if u.scheme == 'https' and u.hostname in {'www.bilibili.com', 'bilibili.com', 'm.bilibili.com'}:
        match = re.fullmatch(r'/video/(BV[0-9A-Za-z]{10})/?', u.path)
        if match:
            return match[1]
    raise SafeError('invalid_video', 'Use a BV identifier or an HTTPS bilibili.com/video/BV… URL.')
