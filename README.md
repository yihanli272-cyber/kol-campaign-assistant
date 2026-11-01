# AI KOL Campaign Decision Assistant

通用的跨平台达人营销决策工作台，帮助用户比较候选、匹配营销目标、优化预算组合并解释决策。PETKIT YumShare Dual-hopper 2 是内置演示案例，不代表品牌隶属、背书或唯一适用品牌。

## 产品体验

- **Campaign Overview**：预算、组合人数、预计触达、互动、点击和转化。
- **Creator Discovery**：52条真实平台账号资料，Instagram 20、TikTok 20、YouTube 12；支持平台筛选、搜索与分页卡片。
- **Creator Evaluation / Shortlist**：六位重点研究候选、历史指标比较、内容方向线索及决策依据。固定名单为 Instagram KOL-014、KOL-006，TikTok KOL-025、KOL-022，YouTube KOL-041、KOL-044。
- **Budget Optimization**：在预算和人数限制内优化整体目标贡献，展示入选与备选取舍。
- **Scenario Simulation**：比较 $3,000 / $5,000 / $7,000，Brand Awareness / Engagement / Conversion，以及保守 / 基准 / 乐观效果假设；区分固定组合重算与重新优化。
- **What-if Analysis**：强制加入备选，查看替换名单和成本、触达、互动、点击、转化差额。
- **Guided Trial**：Welcome → Campaign Brief → Discovery → Evaluation → Optimization → Simulation → Summary。支持前后导航、退出并恢复原 Workspace，以及CSV报告下载。
- **Research Workspace**：完整资料和证据状态的只读研究视图；公开模式不提供审核保存。

产品配置可在界面中修改、下载和重新导入。修改仅保留于当前会话；完整刷新后需重新导入。更换品牌或市场不会自动证明现有宠物候选、受众或规划假设对新任务适用。

## 数据与 Simulation 边界

真实账号历史指标与模拟参数分开保存；52条是平台账号记录，不按同名合并为独立创作者。六位候选属于研究优先名单，不代表人工批准或可合作承诺。资料描述和内容线索不等于已观看、核验原帖；缺失数据不补零，已有检索匹配度不等于转化概率。

报价、触达、模型互动率、CTR、CVR及预测结果均为 **Simulation**。演示参数独立且版本固定，不由历史播放量冒充投放触达；YouTube 采用统一演示合作口径，不声称已区分长视频与 Shorts。累计触达未去重，转化是数学期望，不是真实订单或历史投放效果。保守 / 基准 / 乐观沿用现有0.7 / 1.0 / 1.3倍率，不为制造名单变化而更改数据。

> All campaign costs and performance projections are illustrative planning assumptions, not actual creator quotes or historical campaign results.

使用本地规则及可解释计算，不调用付费AI API。原始工作簿、PDF、私人联系方式和人工审核日志不进入公开仓库。

## 本地启动

依赖见 `requirements.txt`，当前验证环境为 Python 3.13；两个锁定依赖要求 Python 3.11或以上。

```powershell
python -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

新环境可使用 `python -m streamlit run app.py`。打开 http://127.0.0.1:8501/ ，点击“Guided Trial · 新手引导体验”开始七步流程。修改多个模块后建议重启服务。历史兼容入口 `?workspace=legacy` 保留用于回归。

## 部署模式与写入安全

`deployment_config.json` 默认且发布时必须为 `{"mode": "public_demo"}`。缺少配置、解析失败或未知模式均按只读公开模式处理。

- 公共模式在后端拒绝人工审核/证据保存、CSV导入落盘及研究文件生成，即使直接调用保存函数也不能写入。
- 人工审核日志在公开模式不加载；52条公开资料及全部核心规划功能继续可用。
- 配置导入和情景快照只更新当前会话；CSV、JSON下载在内存生成，不覆盖服务端文件。
- 本地审核必须由服务器进程设置 `KOL_DEPLOYMENT_MODE=local_dev`。它不能由浏览器、Campaign导入或session_state开启。

仅供受信任本地开发使用：

```powershell
$env:KOL_DEPLOYMENT_MODE = 'local_dev'
.\.venv\Scripts\python.exe -B -m streamlit run app.py --server.address 127.0.0.1
# 完成本地审核后恢复公开默认
Remove-Item Env:KOL_DEPLOYMENT_MODE -ErrorAction SilentlyContinue
```

不要在公开托管环境设置 `local_dev`。只读保护针对应用业务写入；框架自身的运行日志、缓存不属于人工审核数据持久化。

## 测试和发布前检查

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B -m pip check
.\.venv\Scripts\python.exe -B release_audit.py
```

本轮公开发布准备验证：**135项测试全部通过**（原125项保留，新增10项），用时478.715秒；测试在仅含53项白名单文件、没有原始Excel的临时目录中执行，未跳过测试。`pip check`和白名单核验也已通过。原始Excel导入测试改用 `tests/fixtures/registry_source.json` 的3条合成记录；测试在临时目录生成工作簿，涵盖文本/长数值ID、缺失值、小数与零。样本不来自原始工作簿，不包含真实联系方式，也不进入运行账号库。公开仓库可独立测试，无需原始Excel。

`release_whitelist.txt` 逐项列出可公开文件。`release_audit.py` 只读核对文件存在、导入关系、敏感内容、公开默认配置和Git可见文件；不暂存、不提交、不推送。新增文件应先审核再明确纳入白名单。内部研究报告、派生数据、日志、原始文件及本地备份不发布。

## Streamlit Community Cloud 部署说明

以下是发布准备说明，仓库更新与线上部署需另行确认。

1. 先完成上面的全量测试与白名单检查，复核待提交文件。
2. 在 Community Cloud 的 Create app 中选择仓库 `yihanli272-cyber/kol-campaign-assistant`、分支 `main`、入口 `app.py`。
3. 在 Advanced settings 选择与本地一致的 Python 3.13（以平台实际提供版本为准；最低3.11）。依赖由根目录 `requirements.txt` 安装，主题读取 `.streamlit/config.toml`。
4. 保持 `deployment_config.json` 为 `public_demo`，不要设置本地写入环境变量；本Demo不需要API密钥或Secrets。
5. 发布后验收首页、52人Discovery、六人Shortlist、三类情景、What-if、Guided Trial和CSV下载，并确认Research只读。HTTP 200不能代替页面功能验收。

原始Excel、PDF、`.venv`及本地审核日志无需上传。应用正常启动只读取白名单中的公开CSV和JSON。云端临时磁盘不作为数据存储方案；完整刷新或进程重启会丢失会话修改，应提前下载配置或报告。

官方说明：[部署应用](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)、[依赖管理](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)。
