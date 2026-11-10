"""Run the two frozen voices once after an explicit clean-machine installation."""
import json
import sys
import wave
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pipeline.core import TZ,read_json
from pipeline.workbench import prepare_workbench_audio

def main():
    day=datetime.now(TZ).date().isoformat()
    run=ROOT/'outputs/setup-smoke'/datetime.now(TZ).strftime('run-%Y%m%d-%H%M%S')
    run.mkdir(parents=True,exist_ok=False)
    lines=[dict(text='大家好，我是小序。',anchor='xiaoXu',scene=-1),dict(text='大家好，我是小禾。',anchor='xiaoHe',scene=-1)]
    entries=prepare_workbench_audio(lines,read_json(ROOT/'config/pipeline.json'),run,day)
    for entry in entries.values():
        with wave.open(str(entry['path'])) as audio:
            if audio.getnframes()<=0:raise ValueError('Empty smoke-test voice')
    print('Two-voice smoke test generated. Listen before approving a new installation.')
    print(run)

if __name__=='__main__':main()
