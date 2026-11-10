# 六栏18条与自动章节进度审查

用户2026-11-09指定六栏各3条：头条新闻、科技要闻、AI落地、科研成果、GitHub昨日开源有趣项目、产业观察。头条跨类别先选，整期同一事件只计一次；不足先扩源，仍不足说明缺额。

本次是规范、输入校验与播放器实现，不代表已核实18条新消息。演示使用现有静帧和占位章节，不生成配音或整期新闻。

## 实现

config/pipeline.json六栏目ID/配额作为单一配置，目标及上限18。新版edition使用section_schema_version=1，各条有section/event_id，section_notes记录缺额。校验顺序、配额、事件ID及标题重复，兼容未分栏历史1–8条。语义去重和GitHub昨日首次公开开源仍需原始证据与人工核查，不能用字段校验冒充完成。

pipeline/navigation.py根据实际timeline镜头起止生成watch.html、chapters.json、chapters.vtt和chapters.ffmetadata，拒绝遗漏、间隙、倒序及非法时间。网页底部支持拖动/键盘调整、栏目/逐条跳转、播放暂停、静音和全屏。render在最后转场/快讯合成后生成导航，用-c copy写入MP4章节；组件与产物纳入哈希。run为新成片latest增加player/chapters入口，不改旧latest。

原nau-cea任务通过官方automation_update更新成功，回读确认目标18、先审后导出限制、禁止文字截图。原每天08:00及原目标聊天保留，没有新建任务；旧DAILY-07阻塞解除。

## Full验证与边界

实际运行python -X utf8 -B -m unittest discover -s tests -v，60项通过，含10项新增栏目、时间线、浏览器真实跳转、手机宽及MP4章节测试。FFmpeg测试完整解码通过，写章节前后AAC编码包SHA相同。60份历史输入WAV重算SHA匹配；固定speech配置、旧news.mp4及旧latest保持。桌面和390px宽度截图已目检，可交互演示见demo/watch.html。

OCR not run：ocr v1.13.6可用，但delegate preview因非Git项目失败，改用人工检查源码、调用点与实际产物，不称OCR通过。

本次未写Skill；核查时发现该共享文件被其他工作更新，已记录前后hash，不覆盖、不回滚，也不声称其全局hash不变。Skill是否已确认属于其对应工作的授权范围，本次不作判断。

18条实际采编与整片尚未执行。画面上的条不能直接点击，交互由网页播放器提供；MP4内嵌章节的显示取决于外部播放器。功能演示的章节是占位数据，不作为真实新闻稿。

审查目录：<本机数据根>\review\edition18-navigation-20261109

独立生成播放器（不改视频）：
```powershell
python -m pipeline.navigation --edition 稿件路径 --timeline 最终时间线路径 --output 新播放器目录 --video 视频路径或URL
```
