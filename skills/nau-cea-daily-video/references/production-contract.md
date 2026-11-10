# 素材与表演接口

项目：当前项目根目录。实现及校验以 pipeline/production.py 和当前 edition.json 为准。

## 新闻 media 数组

2026-11-10用户新增硬约束：禁止用自行绘制的SVG、Canvas、HTML/CSS、Pillow等图形代替图片素材，包括LOGO；转PNG/JPG、录视频、模糊铺底或标为“编辑事实图”也不构成例外。真实照片/演示及发布方原始图形须取得原文件；图片重制按任务使用对应图像生成/编辑工具。找不到合格素材应继续补找并如实标记缺素材/未完成，不能用程序图兜底。来源与制作方式须逐素材核查；文件哈希只证明文件一致，不证明素材合格。完整要求见SKILL.md“图片素材不得用程序绘图代替”。

每个元素必须包含：

```json
{
  "kind": "video",
  "path": "../../media/2026-11-08/space-archive.mp4",
  "sha256": "实际原文件的64位SHA256",
  "source_url": "https://原发布机构/实际读过的来源页",
  "asset_url": "https://原站/实际下载文件.mp4",
  "published_at": "2026-08-30T18:56:18+08:00",
  "role": "archive",
  "caption": "载人办/新华社｜08-30资料画面",
  "offset": 7,
  "rights_note": "真实来源与许可状态；本地待发布审阅"
}
```

kind=image/video；入画role只用current/archive，source_capture文字核验截图会被拒绝。archive的caption必须含“资料”。已知素材published_at需带时区；确实未知时仅限archive，published_at=null、media_date_precision=unknown、original_asset_first_publication_unknown=true及非空media_date_note同时填写，不能把HTTP修改时间当首发。path相对于edition.json，也可为真实绝对路径；必须存在且哈希匹配。视频从offset秒开始使用本句实际长度，不默认循环不足的素材；不足则停止，调整起点或换素材。video原声静音，保留主播口播，完整比例与水印保留。输入视频会完整解码，实际片段嵌进视频，不把封面当视频。

每条新闻的逐句口播依次使用media元素，末尾可复用，推荐按语义安排与narration同长的media。render会去重复制原文件到run目录、保存media-sources.json；同一原视频不同offset仍须逐句保留。所有新闻默认必须有源素材，不能无声退回编辑信息图。

## 期级 performance 可选覆盖

当前11月9日18条一期包括NAUCEA双主播开场2句、六屏目录各1句、新闻正文72句、结尾2句，共82句（以后各期依实际正文句数变化），从0编号；以edition_lines实际顺序为准。旧opening_briefs只兼容历史稿，不用于新一期。例：

```json
{
  "performance": {
    "2": {"expression": "presenting", "action": "nod", "focus_ratio": 0.38},
    "13": {"expression": "wave", "action": "greet", "focus_ratio": 0.32}
  }
}
```

expression必须来自对应主播script.js expressionMap且不同于该主播默认姿态。小序normal起止，happy/presenting/thinking等在句中展示；小禾happy起止，wave/encourage/normal等在句中展示。action=nod/greet/hold；0<focus_ratio<1。默认不需要逐句写覆盖，语义规则自动配置。

plan预览以标准化1秒显示选择和比例，不可冒称真实时间；render使用24k PCM实际发声区间绑定：起始姿态→句中焦点姿态与一次小幅动作→句末恢复。timeline.json保存performance_events、speech_intervals、pose_assets/sha256、media/offset和媒体窗口坐标。真实字词时间未知，不承诺关键词逐字同步。

## 输出复用

production-plan.json可供下次审阅及工具接入；标准入口是python -m pipeline.run plan/render。外部WAV复用须满足已有audio_manifest全句文本、顺序、数量及哈希契约，不能拿旧男声复用给新女声。失败保留旧latest和last-failure.json。机器检查更新latest之后仍需独立终检；若审查失败标需修订，不能把latest存在当作终检通过。

仅修改素材/动作时，可用 `python -m pipeline.run render --edition 路径 --audio-manifest 已验证的audio-manifest.json` 复用全句WAV；各WAV path按既有契约相对edition.json，推荐绝对路径。复用必须同时匹配逐字文本、对应主播及实际SHA；改顺序后的主播分配也重验。新增句子串行补生成，再组完整清单，不能部分缺句回退系统声。工作台启动日志使用文件句柄，不用捕获管道等待后台服务退出；low_memory_load仅控制等值加载顺序，不能改权重、参考或合成情绪参数。


## 当前节目结构

config.opening读取已确认8秒开屏及品牌修订授权，CREDITS随交付。edition.section_overviews映射六栏事实概述；programme.section_cards自动取每栏3条当前标题，目录每屏至少6.5秒。programme.insert_interludes在5个栏目边界插入3.4秒独立无正文区间（0.3+2.8+0.3），不叠加在口播上；narration保存对应零PCM，字幕不跨区间，局部performance_events保持。opening.shift_timeline统一顺延shots/interludes/转场帧；navigation由最终timeline生成开屏/开场/目录/18条/5过渡/结尾共32章。实际数量随当期缺额变化，禁止均分造章节。
