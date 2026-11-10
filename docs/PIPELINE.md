> 架构1.0起：当前目录、更新门禁与命令以 ARCHITECTURE.md / REUSE_GUIDE.md 为准。下文D/F盘及outputs/daily路径是历史生产机记录；执行时读取config与pipeline.storage.issue_paths，不复制这些绝对路径。render先待终检，终检后显式publish-current。

> 2026-11-10开场补充：第一句“这里是南京农业大学计算机爱好者协会。”，随后“欢迎收看NJAU-CEA新闻联播。”，之后播报日期；音色沿用固定小序和小禾。

> 2026-11-10用户最新纠正：节目品牌与节目LOGO统一为大写NJAU-CEA（保留连字符），开屏/台标/底栏/转场/口播/图文同步，取代旧NAUCEA。社团全称不变。

> 2026-11-09当前用户规范：六栏目各3条，目标18条；头条先选、全期去重。读取EDITORIAL_POLICY.md新版分栏契约，每期由实际timeline生成watch.html和章节，详见EDITION18_NAVIGATION.md。用户已确认280–300字/分钟试听、最新版同棚新闻页，并明确要求奶白圆角气泡接入正式版；唯一nau-cea-daily-video Skill已同步确认规则。本期合片仍须以实际成片审查结果为准。

> 当前素材规则（2026-11-09）：参考图和入画素材一律拒绝文字截图，内部核验截图不得充当配图或模糊底图。详见[VISUAL_MATERIAL_POLICY.md](VISUAL_MATERIAL_POLICY.md)。旧文中的原文截图仅保留作历史/核验证据描述。

> 最新节目结构：品牌统一NJAU-CEA新闻联播；8秒地球开屏在原双主播之前；详细播报前六屏目录自动展示本期18标题，每屏至少6.5秒，section_overviews逐栏短口播。仅5栏目之间独立插入0.3秒留白＋84帧/2.8秒v4转场＋0.3秒留白；转场显示目的栏目和3标题，无正文人声/字幕/快讯。同栏目直切。旧“覆盖口播且整轨AAC不变”检查停用，改验正文WAV/局部动作不变、独立区间静音及字幕不交叠；所有时间和章节重建。

> 转场视觉更新：用户本聊天最新满版参考已接入assets/transitions/campus-ip-sweep-v4/library.json。右上双LOGO＋NAU CEA、右下8种正比IP动作/场景沿斜边铺满；横切仍84帧/30fps、42帧切点。保留上述栏目边界、播报条与音轨规则，只替换默认素材库；旧成片不自动更新。随机预览及剪辑说明见该目录preview.html与使用说明.md。

# 每日新闻视频工作模式

## 社团名称（2026-11-09用户确认）

中文全称统一使用**南京农业大学计算机爱好者协会**；CEA 英文全称统一使用 **Computer Enthusiasts Association**，其中 E 为 Enthusiasts（爱好者）。后续文稿、署名、介绍和新增设计均沿用此名称。节目品牌保持 **NJAU-CEA 新闻联播**（排版可用 **njau-cea**）。用户提供的历史会徽原图不改写，图内旧文字不作为后续全称依据。

负责人：每日新闻流水线窗口 `01a1b802-3842-7ec3-8a77-c85567c8d7ad`。时区为 Asia/Shanghai。

用户已授权休息期间由此窗口统筹本项目常规技术问题。其他三个项目窗口已通知，并分别提供 [主播素材](ANCHOR_ASSET_HANDOFF.md)、[台标](STUDIO_BRANDING_HANDOFF.md)、[IndexTTS2](INDEXTTS_HANDOFF.md) 交接。文件内容供核实与集成，不自动扩大付费、发消息或发布权限。

## 现在的生产流程

每天北京时间08:00，Codex原生每日任务在此聊天执行下列步骤。新闻覆盖前一天00:00–24:00。图文和视频目标18条：头条新闻、科技要闻、AI落地、科研成果、GitHub昨日开源有趣项目、产业观察各3条，每条有真实素材；单事件不跨栏目重复。缺额先扩源核实，仍不足用section_notes如实记录，不能凑旧闻。详见[每日内容标准](EDITORIAL_POLICY.md)。

1. 阅读本文、`docs/TODO.md`、`config/pipeline.json` 和配音交接最新状态。
2. 执行 `python -m pipeline.run collect --date YYYY-MM-DD`。结果在 `outputs/daily/YYYY-MM-DD/candidates.json`；每个来源独立记录成功、当期数量或错误。候选均标为未经核实。
3. Codex 编辑回源核实，优先官方公告、研究原文、原始采访。筛掉重复事件、过时转载、传闻及无从核对的数字。网页返回 HTTP 200 但正文为反爬验证页时，不得算作已读取原文；可用官方 RSS 全文、官方网页或其他可验证渠道，并记录实际依据。
4. 写当日 `edition.json`。将原文发布日期、事件日期、转载日期分开；默认只纳入原文于前一天发布的新闻。`verified=true` 必须伴随具体 `verification_note`；这个标志来自编辑核实，不代表程序能判断事实真伪。
5. 每条新闻配置原视频、原照片或图形资料 media（拒绝文字截图，见VISUAL_MATERIAL_POLICY.md），附原页、素材日期、用途、说明和SHA256；资料画面明确标注。先执行 `python -m pipeline.run plan --edition outputs/daily/YYYY-MM-DD/edition.json`，无需GPU即可生成逐句素材和表演计划。再执行同路径 render，自动使用固定工作台音色，按实际发声时长绑定句中表情切换和一次小幅动作、句尾恢复。视频素材按各句offset实际播放，完整人物PNG始终整图，不拼接五官。
6. 阅读清单、检查完整解码、尺寸、帧率、音量峰值和字幕边界。查看成片抽出的关键帧。按 `global-self-review` 和 `video-shotcraft` 完成与本期规模匹配的审查；人工试听未执行时写明。修复本期范围内可复现问题，然后重跑对应检查。
7. 全部机器检查通过后，渲染器才更新 `outputs/daily/latest.json` 与当日 `latest.json`。最终视觉审查若失败，应将该期标为需修订，修好重渲，不作为可发布版。定时任务仅保存待发布成片与报告。

## 可直接运行

在项目根目录打开 PowerShell：

```powershell
python -m pipeline.run collect
python -m pipeline.run plan --edition outputs/daily/2026-11-08/edition.json
python -m pipeline.run render --edition outputs/daily/2026-11-08/edition.json
python -m unittest discover -s tests -v
```

`collect` 默认使用北京时间当天日期。也可传 `--date 2026-11-08` 重取那一期覆盖区间；RSS 未必长期保留旧新闻，重跑不能替代归档。

每次渲染独立保存 `run-时分秒-微秒/`，失败不覆盖旧视频。`.render.lock` 拒绝并发渲染。异常进程退出遗留锁时，先读取其中 PID、开始时间和路径，核对进程身份；确定原进程已结束才能处理锁，不根据“很久没更新”删除活锁。

## 稿件格式

可直接以 `outputs/daily/2026-11-08/edition.json` 为样板。核心字段：

- 期级：`date`、`title`、`stories`；可增加 `selection_note`。
- 新闻：`id`、`title`、`published_at`（ISO8601，带时区）、`original_publication_date`、`source_url`、`source_name`、`source_type`、`verified`、`verification_note`、`summary`、`why_it_matters`、`visual_labels`、`narration`。
- `published_at` 必须在覆盖窗口内。只有日期的来源用 `time_precision: "day"`，时间内部以零点归档，画面仅显示日期，不能伪造发布时刻。
- `visual_labels` 需 1–4 个有出处的短标签，每个至多 12 字；用于编辑提炼。新闻画面默认必须提供 media：优先原视频、原照片、原文截图，尽量不用直接AI生成的新闻配图；必要编辑图表必须依据事实且标明。每条素材需 kind、path、sha256、source_url、published_at、role、caption；历史资料 role=archive 且画面说明含“资料”。视频 offset 是每句截取起点，原片段不足时停止而非默认循环。
- `narration` 为逐句数组，每句至多 22 字。顺序即配音、字幕和剪辑顺序。标题至多 26 字。视频字幕字号 64px、正文标题 64px、来源条 36px；程序限制是防溢出的上限，渲染还会检测字幕和标题实际溢出，仍需目检。

## 配音

2026-11-09最新语速要求：两主播正文280–300字/分钟，固定音色不变。speech.pacing已启用；渲染器先对生成/复用的原WAV逐句不变调校准，再量测响度并重排字幕/动作，不能仅把双方基础rate=1.0当成语速相同。普通句优选295、数字/术语句285；计入正常停顿与帧取整，分别验收两位主播和正文。详见[语速规则](SPEECH_PACING.md)。用户只要试听时不导出整片。


默认使用本机 IndexTTS2 工作台，配置为 `config/pipeline.json` 的 `speech.provider=indextts2`。用户于 2026-11-08 明确授权此聊天为两位主播选择音色、提供试听、重配当天视频并作为后续每日默认。实际生成与验收见 [CURRENT_PRODUCTION_REVIEW.md](CURRENT_PRODUCTION_REVIEW.md)。

适配层读取 `配置speech.workbench.state_file` 的实际 URL，服务未开时使用既有启动器；一次原生客户端 `batch` 串行生成全部句子。主播固定参考路径、SHA256和预设以配置为准，文件保存在F盘。用户最新纠正为小序恢复之前的自然男童声boy-v2，小禾使用自然女童声方向girl-v2，固定男童+女童，未经新的明确要求不自行换音色。工作台命名预设用于后续人工操作；生产读取固定参考路径，避免预设在页面被改动后无声漂移。任务清单、读音预览、逐句结果、进度、音色来源和音频哈希随当期落盘。安装与模型状态仍参考 [INDEXTTS_HANDOFF.md](INDEXTTS_HANDOFF.md)。

已有可用音频可通过 `audio_manifest` 接入：期级填写相对 `edition.json` 的 JSON 路径，该 JSON 用从 0 开始的**全部口播句序号**作键，每条包含 `text`、`path`、`voice`，建议附 `sha256`。开场 2 句、新闻正文、结尾 2 句，文本必须完全相同。缺句、失败、截断或哈希变化时整期停止，禁止混用系统声音。外部音频统一转为 PCM 后实测时长，字幕和画面据此重排；来源 WAV 在 F 盘缓存，实际用于剪辑的 PCM 随成片归档。

Windows 系统语音仅作手动备用：明确将 `speech.provider` 改为 `system` 后才使用小序 `Microsoft Kangkang`、小禾 `Microsoft Huihui Desktop`，并使用配置中的 PowerShell 7。生产故障不自动切换。

所有逐句配音先测输入 LUFS 与真峰值，再施加固定线性增益：目标 -18 LUFS、真峰值不高于 -3 dB，峰值约束优先；保留原始 WAV，帧数与采样率必须不变。静音、非有限量测或需要超过 20 dB 放大时拒绝该期。增益与输入量测保存在 timeline 中，防止两主播原始音量相差较大造成忽响忽轻。

## 资源整合

| 现有资源 | 使用方式 |
|---|---|
| `index.html`、`style.css`、`script.js`、`news-media.js` | 截取真实演播室与资讯场景，根目录源码保持原有交互 |
| `script.js` 的 `expressionMap` | 用现行整图角色，不调用退役嘴层或 repaired 素材 |
| `assets/branding/` | 保留校徽与社团 LOGO |
| `assets/references/editorial/HANDOFF.md` 与 `sample/` | 借用来源、逐条配图、回源与日期标准；奶油色/墨绿信息图延续样稿视觉；旧样稿未作为新新闻导入 |
| IndexTTS2 工作台 | 默认使用原生客户端单次串行 batch；参考、参数、WAV 时长和哈希可追溯 |
| Python、Playwright、Pillow、imageio-ffmpeg | 使用本机已有依赖，无新收费 API |

## 每期交付

`news.mp4`：1920×1080、30fps、H.264/AAC。`daily.html` 与 `media-xx` 原照片/视频/截图：配套图文与素材。`media-sources.json`：出处、素材日期、资料用途和哈希。`production-plan.json`：逐句素材与表演计划。`subtitles.srt`、`narration.wav`、逐句配音与 `timeline.json`：可继续剪辑。`edition.json`、`manifest.json`、`audio-analysis.txt`、`contact-sheet.jpg`、`qa-xx.png`：内容、来源、哈希与验收依据。

默认固定机位、逐句素材切换、字幕和双主播交替，无BGM或额外音效。表演按句意选择整图姿态，再绑定到实际发声区间：起始→句中焦点姿态/点头或问候动作→句尾恢复，静音停止动作。触发为发声区间比例近似，未做逐字强制对齐；不冒称骨骼动画或实时口型。可在期级 performance 用句序号覆盖 expression、action、focus_ratio，详情见 [MEDIA_PERFORMANCE_PLAN.md](MEDIA_PERFORMANCE_PLAN.md)。

## 运行条件与故障

原生定时任务需要电脑与 Codex 保持运行、项目磁盘可用；锁屏可继续本地无头渲染，关机或休眠期间不能出片。不额外新建后台轮询器。调度记录见 `docs/PIPELINE_AUTOMATION.json`。

无当期可信消息、配音失败、磁盘不足或解码失败均停止本期交付，保留 `last-failure.json` 和原始运行目录。自动任务记录失败及下一步，不能补写“成功”。不删除旧稿、源素材、其他窗口正在使用的文件或历史成片。

## 可复用技能与固定偏好

全局技能：`skills/nau-cea-daily-video/SKILL.md`，可用 `$nau-cea-daily-video` 调用，包含新闻核实、素材、配音、逐句表演、终检和失败边界。固定声音和参数记录在 `config/pipeline.json`，技能 references/voice-profile.json 为快照；实际生成前验证参考SHA256。小序恢复之前自然男童声boy-v2（Yunxia合成参考，已冻结本地），小禾自然女童声方向girl-v2；女声girl-v3已停用于小序，参考和历史文件保留。情绪参数 emo_mode=2、emo_vector=0,0,0,0,0,0,0,0.65、emo_weight=0.65、seg_tokens=80，双方rate=1.0。

仅修改素材/动作时，可用 `python -m pipeline.run render --edition 路径 --audio-manifest 已验证的audio-manifest.json` 复用全句WAV；各WAV path 按既有契约相对edition.json，推荐使用绝对路径。来源清单会记录并校验，daily默认配置不变。本期重剪复用之前的小序boy-v2男声及上一版小禾girl-v2女童声的14句工作台结果，避免重复GPU任务。

## 每日磁盘入口（2026-11-08更新）

D盘在独立终检截图时不足，现有daily目录被占用，未强制关闭应用或替换旧目录。1900份既有日常产物已复制到<本机数据根>/daily并逐文件SHA验证；D原件全部保留。以后每个新日期采集前，先建F日期目录，在不存在的D日期路径新建目录联接；既有collect/render和原入口不变，实际大文件写F。已实际验证2026-11-09空日期联接，并未生成未来新闻。既有普通日期目录不强改，不删文件/锁。原始新闻素材与独立审查大图分别保存<本机数据根>/media、<本机数据根>/review。详细布局、复制清单和边界见DAILY_STORAGE.json。


## 2026-11-09 固定语音动效修复

网页talking.js原本按实时音量触发voice-active，但离线渲染禁用CSS动画且隐藏主播后只重新叠加整图姿态，未调用粒子层。render.py现固定叠加8个黄绿粒子与2px/1.5px整图轻抖，二者均由本句WAV实测speech_intervals门控：有声触发、静音归位。逐句点头/问候弧线与语义姿态保持独立；timeline记录voice_effects，测试实际渲染帧验证启停、位移与确定性。后续默认render自动执行，无需逐期手动开启网页播放。

来源扩展：config/source-catalog.json登记原始站点，config/pipeline.json新增8个定向发现RSS；参考两页日报的12块回源核查见docs/SOURCE_AUDIT_20261109.md。发现渠道成功不等于事实已核实。


## 2026-11-09 纯净日期生产门禁

以运行时北京时间今天命名，只报昨天完整自然日首发且有新增事实的消息。候选发现时间、转载和更新不能代替首发；日期证据必须实际读取、落盘并核对SHA。edition.stories每条新增date_evidence，字段与例外见EDITORIAL_POLICY.md及DATE_PURITY_20261109.md。plan在配音前拦截缺证据；render拒绝错刊期、今日archive例外和跨日首发。复用成片前也要重验日期证据。

正常命令沿用python -m pipeline.run collect --date YYYY-MM-DD、plan --edition ...、render --edition ...；历史补制另设archive_production=true并显式render --archive，交付明确写历史刊期。今日选题/成片状态以docs/CURRENT_DAY_STATUS.json为准，历史latest不代表今日已经生产。
