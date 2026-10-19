"""Check the installed product from an empty working directory, without a session."""
import json
import os
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path


def main():
    executable=Path(sysconfig.get_path('scripts'))/('bili-agent.exe' if os.name=='nt' else 'bili-agent')
    assert executable.is_file(), 'Installed entry point missing'
    with tempfile.TemporaryDirectory() as directory:
        environment=dict(os.environ)
        environment.pop('PYTHONPATH',None)
        environment['BILI_AGENT_CREDENTIAL_FILE']=str(Path(directory)/'missing-session')
        def call(args, code=0):
            result=subprocess.run([str(executable),*args],cwd=directory,env=environment,
                                  capture_output=True,text=True,timeout=15)
            assert result.returncode==code, 'Unexpected installed command exit code'
            return result.stdout
        version=call(['--version']).strip()
        capabilities=json.loads(call(['capabilities']))
        assert capabilities['ok'] and capabilities['data']['version']==version
        assert len(capabilities['data']['commands'])==48
        assert capabilities['data']['account_writes'] is True
        assert Path(capabilities['data']['implementation_guide']).is_file()
        assert Path(capabilities['data']['sdk_source']).is_file()
        assert json.loads(call(['doctor']))['data']['credential_file_exists'] is False
        assert json.loads(call(['status'],1))['error']['code']=='credential_missing'
        preview=json.loads(call(['like-video','BV13Apt6sEhK','--dry-run']))
        assert preview['data']['request_sent'] is False and preview['effect']=='account_write'
        missing=json.loads(call(['like-video','BV13Apt6sEhK'],1))
        assert missing['error']['code']=='credential_missing' and missing['error']['outcome']=='not_sent'
        dm=json.loads(call(['dm-send','123','text','--dry-run']))
        assert dm['data']['request_sent'] is False and dm['route']=='local'
        assert json.loads(call(['dm-sessions'],1))['error']['code']=='credential_missing'
        assert json.loads(call(['unknown-command'],1))['error']['code']=='invalid_arguments'
        result=subprocess.run([sys.executable,'-c','from bili_agent import Client, AgentError; Client(credential=None)'],
                              cwd=directory,env=environment,capture_output=True,text=True,timeout=15)
        assert result.returncode==0, 'Installed SDK import failed'
    print(f'Installed {version}: entry point, discovery, docs, SDK and missing-session handling passed')


if __name__ == '__main__':
    main()
