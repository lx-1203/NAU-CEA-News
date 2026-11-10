"""Mandatory daily-orchestration gate; historical render contracts stay readable."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.core import ROOT,read_json,sha256,write_json
from pipeline.programme import section_cards
from pipeline.workbench import edition_lines
from pipeline.opening import load_opening


def validate_current_programme(edition,config):
    if edition.get('title')!=config['programme']['brand']:raise ValueError('本期节目品牌必须与当前配置一致')
    cards=section_cards(edition)
    overviews=edition.get('section_overviews')
    if not isinstance(overviews,dict) or set(overviews)!={c['id'] for c in cards}:
        raise ValueError('缺少当期全部栏目总览，禁止回退旧叠加转场结构')
    if any(not isinstance(t,str) or not t.strip() or len(t)>22 for t in overviews.values()):raise ValueError('每栏目总览口播需为22字内文本')
    if config.get('programme',{}).get('category_transition')!='independent_silent_interlude':raise ValueError('栏目切换必须独立于正文口播')
    if float(config.get('programme',{}).get('overview_minimum_seconds',0))<6.5:raise ValueError('目录阅读时间不足')
    if any('秾好' in line['text'] or '极好' in line['text'] for line in edition_lines(edition)):raise ValueError('口播残留旧节目名')
    return dict(status='passed',stories=len(edition['stories']),overview_screens=len(cards),overview_titles=sum(len(c['titles']) for c in cards),category_interludes=max(0,len(cards)-1),mode='independent_silent_interludes')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--edition',type=Path,required=True);parser.add_argument('--output',type=Path);args=parser.parse_args()
    config=read_json(ROOT/'config/pipeline.json');result=validate_current_programme(read_json(args.edition),config)
    if not load_opening(config):raise ValueError('当前默认开屏未启用')
    result['edition_sha256']=sha256(args.edition)
    if args.output:write_json(args.output,result)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
