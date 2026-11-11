"""Local path relocation and empty next-episode template; no invented news."""
import argparse
import copy
import os
import sys
from datetime import datetime
from pathlib import Path
from .core import ROOT, TZ, coverage, read_json, write_json
from .storage import issue_paths,record_task


def portable_config(source, root):
    root=Path(root).resolve();config=copy.deepcopy(source)
    wb=config['speech']['workbench'];studio=root/'runtime/IndexTTS2-Studio'
    wb.update(project_dir=str(studio),state_file=str(studio/'logs/workbench-service.json'),
              start_script=str(root/'scripts/start_workbench.ps1'),
              client=str(studio/'skills/indextts2-tts/scripts/tts_client.py'),
              client_config_dir=str(root/'runtime/client-config'),output_root=str(root/'outputs/speech'))
    for anchor,voice in wb['voices'].items():voice['reference']=str(root/f'assets/voices/{anchor}/reference.wav')
    config['speech_shell']='powershell.exe'
    config['browser_channel']=None
    config['editorial_policy']['source_reference']='assets/references/editorial/HANDOFF.md'
    config['portable_profile']=True
    if config.get('opening'):
        # Export includes the approved original and relative approval metadata.
        config['opening']=dict(enabled=source['opening'].get('enabled',False),approval=str(root/'assets/opening/APPROVED.json'))
    if config.get('outro'):
        config['outro'] = dict(enabled=source['outro'].get('enabled', False), package='assets/outro')
    if config.get('transitions'):
        config['transitions'] = dict(library='assets/transitions/campus-ip-sweep-v4/library.json')
    return config


def new_edition(day):
    previous=coverage(day)[0].date().isoformat()
    policy=read_json(ROOT/'config/pipeline.json')['editorial_policy']
    stories=[]
    for section in policy['sections']:
        for i in range(section['count']):
            stories.append(dict(id=f'{section["id"]}-{i+1}',section=section['id'],event_id='',title='',
                original_publication_date=previous,published_at='',source_url='',source_name='',
                verified=False,verification_note='',summary='',why_it_matters='',visual_labels=[],narration=[],media=[]))
    return dict(date=day,title='NJAU-CEA 新闻联播',section_schema_version=1,stories=stories,section_notes={},
                editorial_status='empty_template_requires_source_verification_not_publishable')


def main():
    parser=argparse.ArgumentParser(description='可迁移配置与下一期空白模板')
    parser.add_argument('action',choices=['configure','new'])
    parser.add_argument('--date',default=datetime.now(TZ).date().isoformat())
    parser.add_argument('--keep-existing',action='store_true')
    args=parser.parse_args()
    from .updates import ensure_current
    if ensure_current(ROOT).get('rerun_required'):
        os.execv(sys.executable,[sys.executable,*sys.orig_argv[1:]])
    if args.action=='configure':
        path=ROOT/'config/pipeline.json';source=read_json(path)
        if not source.get('portable_profile'):raise ValueError('只在复用包内迁移配置，保留当前生产机的配置')
        write_json(path,portable_config(source,ROOT));print('Portable paths configured.');return
    path=issue_paths(args.date,create=True)['editorial']/'edition.json'
    if path.exists():
        if args.keep_existing:print('Existing edition preserved: '+str(path));return
        raise FileExistsError('稿件已存在，未覆盖：'+str(path))
    write_json(path,new_edition(args.date))
    record_task(args.date,'editorial','empty_template_requires_verification')
    print('EDITORIAL TEMPLATE: '+str(path))


if __name__=='__main__':main()
