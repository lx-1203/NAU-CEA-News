"""Start the pinned portable studio without killing any existing process."""
import argparse
import json
import os
import socket
import subprocess
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def health(url):
    request=urllib.request.Request(url+'/api/v1/health')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request,timeout=2) as response:
        data=json.load(response)
    return data.get('ok') is True or data.get('status')=='ok'

def start(no_browser=False):
    config=json.loads((ROOT/'config/pipeline.json').read_text('utf8'))
    wb=config['speech']['workbench'];studio=Path(wb['project_dir']).resolve();state=Path(wb['state_file'])
    if state.exists():
        data=json.loads(state.read_text('utf8-sig'))
        if data.get('root')==str(studio) and data.get('url','').startswith('http://127.0.0.1:'):
            try:
                if health(data['url']):
                    if not no_browser:webbrowser.open(data['url']+'/longform')
                    print(data['url']+'/longform');return data
            except OSError:pass
    python=studio/'.venv/Scripts/python.exe'
    if not python.exists():raise RuntimeError('Run first_run.bat to install the workbench first')
    for port in range(7861,7900):
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',port));break
            except OSError:continue
    else:raise RuntimeError('No free workbench port; other processes preserved')
    logs=studio/'logs';logs.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8',NLTK_DATA=str(ROOT/'runtime/cache/nltk'),HF_HOME=str(ROOT/'runtime/cache/huggingface'),TORCH_HOME=str(ROOT/'runtime/cache/torch'))
    with (logs/'workbench-stdout.log').open('ab') as out,(logs/'workbench-stderr.log').open('ab') as err:
        process=subprocess.Popen([str(python),'server.py','--host','127.0.0.1','--port',str(port),'--fp16','--s2mel_fp16','--w2v_fp16','--gpt_batch','0'],cwd=studio,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    data=dict(pid=process.pid,url=f'http://127.0.0.1:{port}',root=str(studio),port=port)
    for _ in range(90):
        if process.poll() is not None:raise RuntimeError('Workbench exited; inspect runtime/IndexTTS2-Studio/logs')
        try:
            if health(data['url']):break
        except OSError:pass
        time.sleep(1)
    else:raise RuntimeError('Workbench start timed out; process and logs preserved')
    state.parent.mkdir(parents=True,exist_ok=True);state.write_text(json.dumps(data),encoding='utf8')
    if not no_browser:webbrowser.open(data['url']+'/longform')
    print(data['url']+'/longform');return data

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--no-browser',action='store_true');start(p.parse_args().no_browser)
