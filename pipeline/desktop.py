"""One local entry: studio HTTP preview + speech service + daily command menu."""
import functools
import http.server
import os
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from .core import ROOT,TZ,read_json
from .storage import issue_paths


def main():
    from .updates import ensure_current
    if ensure_current(ROOT).get('rerun_required'):
        os.execv(sys.executable,[sys.executable,*sys.orig_argv[1:]])
    os.chdir(ROOT)
    os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'runtime/browsers')
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}'
    webbrowser.open(url+'/index.html')
    config=read_json(ROOT/'config/pipeline.json')
    try:
        subprocess.run([config['speech_shell'],'-NoProfile','-File',config['speech']['workbench']['start_script']],check=True)
    except (OSError,subprocess.CalledProcessError):
        print('Speech workbench unavailable. Run first_run.bat; collection and editing remain available.')
    print('Studio: '+url+'/index.html')
    print('1 = prepare next episode and collect candidates')
    print('2 = open editorial instructions')
    print('3 = plan and render a reviewed edition')
    print('4 = upload reviewed manuscript to GitHub')
    print('5 = retry pending GitHub manuscripts')
    print('Q = quit this local preview (speech workbench is left running)')
    try:
        while True:
            action=input('Select: ').strip().lower()
            if action=='q':break
            day=datetime.now(TZ).date().isoformat()
            edition=issue_paths(day,create=True)['editorial']/'edition.json'
            review=edition.with_name('editorial-review.json')
            if action=='1':
                if not edition.exists():subprocess.run([sys.executable,'-m','pipeline.portable','new','--date',day],check=True)
                subprocess.run([sys.executable,'-m','pipeline.run','collect','--date',day],check=True)
                print('Candidates need source verification and editorial writing; they are not a finished script.')
            elif action=='2':webbrowser.open(url+'/docs/NEXT_EPISODE_PROMPT.md')
            elif action in {'3','4'}:
                if not edition.exists() or not review.exists():
                    print('A verified edition and matching editorial-review.json are required.');continue
                receipt=read_json(review)
                from .core import sha256
                if (receipt.get('status')!='passed' or receipt.get('edition_sha256')!=sha256(edition)
                    or any(receipt.get(k) is not True for k in ['facts_checked','date_checked','dedup_checked','narration_checked'])):
                    print('The review does not match the current edition. Re-review before production.');continue
                commands=[['plan'],['render']] if action=='3' else [['archive']]
                for command in commands:
                    args=[sys.executable,'-m','pipeline.run',*command,'--edition',str(edition)]
                    if action=='4':args += ['--review',str(review)]
                    subprocess.run(args,check=True)
            elif action=='5':subprocess.run([sys.executable,'-m','pipeline.run','archive','--retry-pending'],check=True)
            else:print('Choose 1, 2, 3, 4, 5 or Q.')
    except (EOFError,KeyboardInterrupt):pass
    finally:server.shutdown();server.server_close()


if __name__=='__main__':main()
