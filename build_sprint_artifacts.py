"""Materialize offline AI/assisted research separately, without overwriting sources."""
from pathlib import Path
import argparse
import json

import pandas as pd

from creator_registry import load_registry, audit_registry, REGISTRY_DIR
from sprint_research import screen_accounts, deep_research, score_registry
from sprint_decision import sandbox_assumptions, adapt_model, safe_csv, scenario_suite


def build(output=REGISTRY_DIR / 'sprint_research'):
    from deployment_policy import require_server_write
    require_server_write('生成本地研究文件')
    output = Path(output)
    if output.exists():
        raise FileExistsError('研究输出目录已存在；请用 --output 指定新的版本目录，禁止覆盖。')
    tables = load_registry()
    screen = screen_accounts(tables['accounts'])
    deep = deep_research(screen)
    model = adapt_model(tables, screen, sandbox=True)
    checklist = pd.DataFrame([dict(creator_id=r.creator_id, platform=r.platform, handle=r.handle,
        requested_post_slot=slot, post_url='', post_date='', visible_views='', visible_likes='', visible_comments='',
        status='待人工核验', collection_scope='尚未采集；空白表示未知，非0',
        verification_tasks='原帖归属/日期/标题或描述/可见指标；是否干粮喂养、智能设备、双仓、多猫、测评；注明是否观看视频')
        for r in deep.itertuples() for slot in (1, 2, 3)])
    attempts = pd.DataFrame([
        dict(source_url='https://www.youtube.com/channel/UCeeD6_kIJw867W79uK9wdMg/videos', creator_id='KOL-041', result='仅返回页脚，无视频条目，不能分析标题/内容', data_type='access_attempt'),
        dict(source_url='https://www.instagram.com/ivythegreykitty/', creator_id='KOL-005', result='获取失败，不重复尝试', data_type='access_attempt'),
        dict(source_url='https://www.tiktok.com/@itscookiecat/video', creator_id='KOL-021', result='定向搜索返回 robots 限制；不是原帖URL，不作为内容证据', data_type='search_access_limit'),
        dict(source_url='https://www.modash.io/content-library/brands/petlibro-examples', creator_id='KOL-006', result='仅二手品牌内容索引，未取得可追溯原帖URL，不纳入原帖表或实测指标', data_type='secondary_lead_only'),
    ])
    frames = {'ai_screening.csv': screen, 'ai_focus_research.csv': deep,
              'manual_verification_checklist.csv': checklist, 'public_access_attempts.csv': attempts,
              'sandbox_assumptions.csv': sandbox_assumptions(tables['accounts'], screen),
              'creator_scores.csv': score_registry(tables, screen, model=model),
              'scenario_comparison.csv': scenario_suite(model).assign(planning_mode='sandbox_unapproved', model_data_type='simulated')}
    output.mkdir(parents=True, exist_ok=False)
    for name, frame in frames.items():
        with (output / name).open('xb') as stream:
            stream.write(safe_csv(frame))
    summary = dict(screened_accounts=len(screen), source_level_focus_analyses=len(deep),
                   ai_analyzed_original_posts=0, watched_videos=0,
                   human_pending_accounts=52, formal_eligible_accounts=int(audit_registry(tables).model_eligible.sum()),
                   method='offline transparent rules; no live AI API; source descriptions only',
                   simulated_assumptions='independent teaching presets; not actual creator quotes or performance')
    with (output / 'summary.json').open('x', encoding='utf-8') as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=REGISTRY_DIR / 'sprint_research')
    print(json.dumps(build(parser.parse_args().output), ensure_ascii=False, indent=2))
