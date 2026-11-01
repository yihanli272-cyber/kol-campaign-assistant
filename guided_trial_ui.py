"""Session-only guided presentation of the existing PETKIT planning journey."""
from copy import deepcopy
import json
import pandas as pd
import streamlit as st
from showcase_ui import (demo_model, discovery_records, render_discovery, scenario_results,
                         public_export, selection_text, METRICS)
from sprint_decision import safe_csv, selection_explanations
from portfolio import OUTCOME_COLUMNS
from ui_layout import value_chart, outcome_charts

STEPS=('Welcome','Campaign Brief','Creator Discovery','Creator Evaluation',
       'Budget Optimization','Scenario Simulation','Campaign Summary')
LEVELS=('保守','基准','乐观')
VIEW_KEYS=('discovery_platform','discovery_query','discovery_page','trial_compare')


def open_trial():
    st.session_state['trial_expert_state']={key:deepcopy(value) for key,value in st.session_state.items()
        if (key.startswith(('sprint_','campaign_','discovery_')) or key=='presentation_mode')
        and key!='campaign_config_upload'}
    st.session_state['trial_active']=True
    st.session_state['trial_step']=1


def leave_trial():
    save_views()
    for key,value in st.session_state.get('trial_expert_state',{}).items():
        st.session_state[key]=deepcopy(value)
    st.session_state['trial_active']=False


def save_views():
    stored=st.session_state.setdefault('trial_views',{})
    for key in VIEW_KEYS:
        if key in st.session_state:
            stored[key]=deepcopy(st.session_state[key])


def move_step(step):
    save_views()
    st.session_state['trial_step']=max(1,min(len(STEPS),step))


def initialize(defaults):
    if 'trial_parameters' not in st.session_state:
        st.session_state['trial_parameters']={**deepcopy(defaults),'budget':5000,
                                               'objective':'Brand Awareness','level':'基准'}
    st.session_state.setdefault('trial_step',1)
    return st.session_state['trial_parameters']


def store_parameter(field, widget):
    st.session_state['trial_parameters'][field]=st.session_state[widget]


def parameter_controls(parameters):
    # Canonical dict survives Streamlit's cleanup of widgets absent on other steps.
    for field in ('budget','objective','level'):
        st.session_state['trial_'+field+'_widget']=parameters[field]
    st.number_input('Trial Campaign Budget · Simulation USD',min_value=0,max_value=10000,step=100,
                    key='trial_budget_widget',on_change=store_parameter,args=('budget','trial_budget_widget'))
    st.selectbox('Trial Marketing Objective',list(OUTCOME_COLUMNS),key='trial_objective_widget',
                 on_change=store_parameter,args=('objective','trial_objective_widget'))
    st.selectbox('Trial Performance Assumptions · Simulation',LEVELS,key='trial_level_widget',
                 on_change=store_parameter,args=('level','trial_level_widget'))


def trial_results(tables, screen, parameters):
    """Select an existing scenario result; no alternative forecast formulas."""
    model,config=demo_model(tables,screen)
    baseline,budgets,objectives,effects=scenario_results(model,parameters['budget'],parameters['objective'])
    chosen=next(optimized for label,_,_,optimized in effects if label==parameters['level'])
    return model,config,baseline,budgets,objectives,effects,chosen


def show_plan(result, handles, objective):
    st.write('**模拟推荐组合：** '+selection_text(result,handles))
    for col,key in zip(st.columns(3),('spent_usd','target_reach','conversions')):
        label='模拟支出 · USD' if key=='spent_usd' else METRICS[key]+' · Simulation'
        col.metric(label,f'{result.metrics[key]:,.2f}')
    used=result.metrics['spent_usd']/result.metrics['budget_usd'] if result.metrics['budget_usd'] else 0
    st.progress(min(used,1.),text=f'Simulation · 预算使用率 {used:.1%}')
    if not result.selected.empty:
        frame=result.selected.copy()
        frame['账号']=frame.creator_id.map(handles)
        value_chart(frame,'账号','execution_cost_usd','入选达人预算分配 · Simulation','USD',horizontal=True)
        value_chart(frame,'账号',OUTCOME_COLUMNS[objective],'入选达人目标贡献 · '+objective,'Simulation',horizontal=True)
    for key in ('engagements','clicks'):
        st.write(f'{METRICS[key]} · Simulation：{result.metrics[key]:,.2f}')


def render_trial(tables, screen, defaults, supplement_path):
    parameters=initialize(defaults)
    step=st.session_state['trial_step']
    with st.sidebar:
        st.subheader('Guided Trial')
        st.caption('当前体验参数保存在本会话；退出不会覆盖 Expert Workspace 配置。')
        st.button('Exit Guided Trial · Expert Workspace',key='trial_exit',on_click=leave_trial)
    st.subheader(f'Step {step} / 7 · {STEPS[step-1]}')
    st.progress((step-1)/6,text=f'体验进度 · {step} / 7')
    if step==1:
        st.write('使用 PETKIT 示例体验：创建营销任务 → 浏览跨平台达人 → 比较候选 → 优化预算 → 测试情景 → 导出决策报告。')
        st.caption('无需上传数据。52条账号用于 Discovery，预算规划沿用现有六位候选及独立 Simulation 参数。体验不会批准任何账号。')
        left,right=st.columns(2)
        left.button('Start Guided Trial',key='trial_start',on_click=move_step,args=(2,),type='primary')
        right.button('Explore Workspace',key='trial_explore',on_click=leave_trial)
        return
    st.caption(f"{parameters['brand']} · {parameters['product']} · {parameters['market']}")
    if step==2:
        st.write('**Campaign Brief** · 预设 PETKIT 案例，可直接继续，也可调整本次体验参数。')
        st.write(f"Product：{parameters['product']} · Market：{parameters['market']}")
        parameter_controls(parameters)
    elif step==3:
        for key,value in st.session_state.get('trial_views',{}).items():
            if key.startswith('discovery_') and key not in st.session_state:
                st.session_state[key]=value
        render_discovery(discovery_records(tables['accounts'],supplement_path))
    else:
        model,config,baseline,budgets,objectives,effects,result=trial_results(tables,screen,parameters)
        st.caption(config['notice'])
        st.caption(f"当前方案：${parameters['budget']:,.0f} · {parameters['objective']} · {parameters['level']}假设")
        handles=tables['accounts'].set_index('creator_id').handle.to_dict()
        if step==4:
            st.caption('Shortlist 固定为现有六位候选。历史指标用于比较；内容方向为资料线索，不表示已观看原帖或完成合作。')
            if 'trial_compare' not in st.session_state and 'trial_compare' in st.session_state.get('trial_views',{}):
                st.session_state['trial_compare']=st.session_state['trial_views']['trial_compare']
            ids=st.multiselect('Trial 双人比较',model.creator_id.tolist(),default=['KOL-014','KOL-006'],
                               max_selections=2,key='trial_compare',format_func=lambda cid:'@'+handles[cid])
            records=discovery_records(tables['accounts'],supplement_path)
            compared=records.loc[records.creator_id.isin(ids)]
            for field,title,unit in [('reported_followers','历史粉丝数','人'),('reported_mean_views','历史平均播放','次'),
                                      ('reported_median_views','历史中位播放','次'),('reported_mean_engagement_rate','历史互动率','比率')]:
                value_chart(compared,'handle',field,title,unit,horizontal=True)
            reasons=selection_explanations(tables,screen,result,parameters['objective']).set_index('creator_id')
            topics=screen.set_index('creator_id')
            for cid in model.creator_id:
                with st.container(border=True):
                    st.markdown(f'**@{handles[cid]} · {topics.loc[cid,"platform"]}**')
                    st.write('内容方向（资料线索）：'+topics.loc[cid,'categories'])
                    st.caption('当前 Simulation 决策依据：'+reasons.loc[cid,'reason'])
        elif step==5:
            st.caption('现有优化器在当前预算与最多6人约束下最大化所选营销目标；不按粉丝数直接排序。')
            show_plan(result,handles,parameters['objective'])
        elif step==6:
            parameter_controls(parameters)
            st.caption('预算与目标比较使用基准假设；效果比较使用同一预算与目标。各类情景独立比较，不覆盖原始基准。')
            for title,plans in [('Budget Scenario',budgets),('Marketing Objective',objectives)]:
                with st.expander(title,expanded=True):
                    outcome_charts(pd.DataFrame([dict(情景=label,**plan.metrics) for label,plan in plans]),'情景',title)
                    for label,plan in plans:
                        st.write(f'**{label}** · '+selection_text(plan,handles))
            with st.expander('Performance Assumptions · Simulation',expanded=True):
                rows=[]
                for label,_,fixed,optimized in effects:
                    for mode,plan in [('固定基准组合',fixed),('重新优化',optimized)]:
                        rows.append(dict(情景=label,计算方式=mode,**plan.metrics))
                    st.write(f'**{label}** · '+selection_text(optimized,handles))
                for field,title in [('clicks','预计点击'),('conversions','预计转化')]:
                    value_chart(pd.DataFrame(rows),'情景',field,title+' · Simulation','次',group='计算方式',line=True)
                st.caption('保守 / 基准 / 乐观沿用现有0.7 / 1.0 / 1.3倍率。固定组合保留基准名单，重新优化再次执行原优化器；名单可能不变。')
        elif step==7:
            show_plan(result,handles,parameters['objective'])
            st.write(f"决策摘要：在 ${parameters['budget']:,.0f} 预算内，以 {parameters['objective']} 为目标，采用{parameters['level']}假设。组合及预测来自现有模型；触达未去重，转化为数学期望。")
            exported=public_export(result,config,parameters['objective'])
            exported['assumption_level']=parameters['level']
            for field in ('brand','product','market'):
                exported['campaign_'+field]=parameters[field]
            st.download_button('下载 Trial Campaign Report · CSV',safe_csv(exported),'trial_campaign_simulation.csv','text/csv',key='trial_report')
            st.download_button('下载 Trial Campaign 配置',json.dumps(parameters,ensure_ascii=False,indent=2).encode('utf-8'),
                               'trial_campaign_config.json','application/json',key='trial_config_download')
            st.success('完整体验已完成。可返回调整参数，或进入 Expert Workspace 自由探索。')
    previous,next_column=st.columns(2)
    previous.button('Previous',key='trial_previous',on_click=move_step,args=(step-1,))
    if step<7:
        next_column.button('Continue',key='trial_continue',on_click=move_step,args=(step+1,),type='primary')
    else:
        next_column.button('Finish · Explore Workspace',key='trial_finish',on_click=leave_trial,type='primary')
