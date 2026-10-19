"""Fail when release archives contain account exports, caches or unsafe paths."""
import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


FORBIDDEN_DIRS = {'.git', '.venv', '__pycache__', 'data', 'build', 'dist'}
FORBIDDEN_SUFFIXES = {'.json', '.jsonl', '.png', '.log', '.pyc', '.sqlite', '.db'}


def check_paths(names):
    for name in names:
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or '\\' in name
                or any(part in FORBIDDEN_DIRS and not (part == 'data' and index > 0
                       and path.parts[index-1].endswith('.data')
                       and path.parts[index+1:index+3] == ('share','bili-agent'))
                       for index, part in enumerate(path.parts))
                or path.suffix.lower() in FORBIDDEN_SUFFIXES
                or path.name == '.env' or path.name.startswith('.env.')):
            raise ValueError('Release contains a forbidden or unsafe member')


def audit(path):
    if path.suffix == '.whl':
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
        required = ['bili_agent/cli.py', 'bili_agent/sdk.py', 'bili_agent/login.py', 'bili_agent/messaging.py', 'bili_agent/network.py',
                    'docs/IMPLEMENTATION.md', 'docs/AGENT_GUIDE.md', 'licenses/LICENSE', 'licenses/NOTICE.md']
    elif path.name.endswith('.tar.gz'):
        with tarfile.open(path, 'r:gz') as archive:
            members = archive.getmembers()
            if any(not (member.isfile() or member.isdir()) for member in members):
                raise ValueError('Source archive contains links or special files')
            names = [member.name for member in members]
        required = ['pyproject.toml','README.md','LICENSE','NOTICE.md','CONTRIBUTING.md','CHANGELOG.md',
                    'src/bili_agent/sdk.py','src/bili_agent/messaging.py','src/bili_agent/network.py','docs/IMPLEMENTATION.md','tests/test_sdk.py','tests/test_messaging.py','tests/test_network.py',
                    'scripts/smoke_install.py','.github/workflows/ci.yml']
    else:
        raise ValueError('Unsupported release archive')
    check_paths(names)
    for suffix in required:
        if not any(name == suffix or name.endswith('/'+suffix) for name in names):
            raise ValueError('Required release member missing: '+suffix)
    if any(name.endswith('/research.py') or name.endswith('/models.py') for name in names):
        raise ValueError('Removed application modules appeared in release')
    return len(names)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    files=sorted(args.directory.glob('*.whl'))+sorted(args.directory.glob('*.tar.gz'))
    if not files or not any(file.suffix=='.whl' for file in files) or not any(file.name.endswith('.tar.gz') for file in files):
        parser.error('Both a wheel and source archive are required')
    for path in files:
        print(f'{path.name}: {audit(path)} members, archive audit passed')


if __name__ == '__main__':
    main()
