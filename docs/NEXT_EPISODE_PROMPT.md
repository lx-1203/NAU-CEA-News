> 架构1.0起：当前目录、更新门禁与命令以 ARCHITECTURE.md / REUSE_GUIDE.md 为准。下文D/F盘及outputs/daily路径是历史生产机记录；执行时读取config与pipeline.storage.issue_paths，不复制这些绝对路径。render先待终检，终检后显式publish-current。

# 给下一期编辑助手的指令

在当前解压的新闻项目根目录工作，不使用原制作机的D/F盘绝对路径。先读config/pipeline.json、docs/EDITORIAL_POLICY.md、docs/VISUAL_MATERIAL_POLICY.md和docs/PUBLICATION.md。

按Asia/Shanghai今天刊期采集，覆盖昨天完整自然日。先运行python -m pipeline.run collect --date 当天日期。目标六栏目各3条、18个不同事件：headlines、technology、applications、research、github、industry。先选头条，从其他栏目剔除同一事件。GitHub栏目核对昨天首次公开开源，旧仓库Release和热榜时间不能代替。确实不足先扩源，仍不足在section_notes记录。

逐条实际读取原始来源，核实首发时区、事件或新增事实日期、数字、归因。把实际读过的原文存为UTF-8，并按date_evidence契约记录路径、SHA、原始日期文本、event_date及说明。验证页和搜索摘要不当作已读原文。只有完成核实才verified=true。

在outputs/daily/当天日期/edition.json写稿；使用section_schema_version=1，各条section和event_id完整。题目≤26字，每句口播≤22字，整条可以多句。先说明发生什么，再解释具体变化和读者关联。删除编辑过程、免责和空泛收尾；企业说法有归因、预发布保留状态、计划不用完成时。初稿按agent内写作与润色参考整理，再回查原文。

每条配置真实图片/视频/图形资料，不使用文字截图。记录来源、素材日期、用途和SHA；历史资料明确标资料，不能假装新事件现场。同一演播室风格，大素材、侧边主播、清楚的标题/要点/来源；待确认设计不擅自转正。

对当前稿进行事实、日期、去重、口播审查。实际通过后写editorial-review.json：status=passed、edition_sha256为当前edition真实SHA256、facts_checked/date_checked/dedup_checked/narration_checked均为true，并写审查依据。不要因为需要上传就伪造通过。运行python -m pipeline.run archive --edition 稿件路径 --review 审查文件路径，把新闻稿归档到已配置公开仓库；失败保留待重试记录，不冒称上传成功。

若用户仍要求先看稿/新闻页，则停在审阅材料，不生成新配音或整片。得到对应生产授权后运行plan和render。固定小序男童boy-v2、小禾女童girl-v2，参数和参考SHA以本机config为准；工作台串行，不与别的任务抢GPU。每句语义表情动作绑定真实发声区间，静音停止，不拼脸嘴。

终检完整解码、字幕边界、峰值、哈希、实际抽帧、两位听音及逐句动作。保存MP4、图文、来源、字幕、音轨、时间线、章节和watch.html，视频只留待发布。新闻稿上传授权不自动扩大成视频或素材对外发布授权。
