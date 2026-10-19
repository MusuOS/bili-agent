import json
import os
from pathlib import Path


class SafeError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


def credential_path(value=None):
    explicit = value or os.environ.get('BILI_AGENT_CREDENTIAL_FILE')
    if explicit:
        return Path(explicit).expanduser()
    native = Path('~/.config/bili-agent/credential.json').expanduser()
    legacy = Path('~/.bilibili-cli/credential.json').expanduser()
    return native if native.exists() or not legacy.exists() else legacy


def load_credential(path, required=False):
    if not path.exists():
        if required:
            raise SafeError('credential_missing', 'Run bili-agent login, or provide a local saved session using --credential-file.')
        return None
    try:
        raw = json.loads(path.read_text())
        allowed = ('sessdata', 'bili_jct', 'buvid3', 'buvid4', 'dedeuserid', 'ac_time_value')
        if not isinstance(raw, dict) or not isinstance(raw.get('sessdata'), str) or not raw['sessdata']:
            raise ValueError()
        values = {k: raw[k] for k in allowed if k in raw}
        if any(not isinstance(v, str) for v in values.values()):
            raise ValueError()
    except (ValueError, OSError):
        raise SafeError('credential_invalid_file', 'Saved session cannot be read; its contents were not modified.') from None
    from bilibili_api import Credential
    return Credential(**values)
