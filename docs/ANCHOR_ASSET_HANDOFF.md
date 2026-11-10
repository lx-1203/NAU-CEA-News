# 主播素材与演播室交接

记录日期：2026-11-08（Asia/Shanghai）。供每日新闻流水线集成读取。

## 当前状态

本窗口已完成原授权素材工作，目前没有待实施项。最新用户反馈为小禾“眨眼 / 招手 / 鼓劲”看不出区别；检查当前三个按钮分别加载不同 PNG 后，用户明确回复“我看错了”，此问题关闭，本轮未修改演播室源码或人物素材。

当前入口为项目根目录 `index.html`。`script.js` 的 `expressionMap` 是现行素材映射的唯一依据，共 14 种人物状态。不要根据旧目录批量挑选 PNG。

- 小序：normal、happy、surprised、thinking、serious、presenting、thumbsup。
- 小禾：normal、happy、excited、shy、wink、wave、encourage。
- 新动作完整图：`assets/characters/anchors/gestures-v2/`，来源和 SHA256 见其中 `sources.json`。
- 其余现行图：`assets/characters/anchors/generated/`，来源见 `provenance.json`。
- 小序惊讶图已整张重新生成，手掌各五指；见 `gestures-v2/FINGER_CORRECTION.md`。

## 用户已明确确定的表现方式

人物直接替换完整表情图片。不得切割、拼接或补贴旧眉毛、嘴巴、手等局部来做一致性。动作要有变化，人设、脸型、比例与服装保持统一。原表情切换弹跳必须保留。

当前说话方式是实际音频音量驱动“粒子特效 + 图片轻抖”；静音、停顿、暂停或结束时停止。无需启用口型序列帧或独立嘴层。独立嘴层旧方案保存在 `outputs/archive-mouth-layer-20261108/`，不要误用到当前渲染。`anchors/repaired/` 中旧拼接产物也已退役。

## 可供流水线调用的现有入口

- `changeExpression('xiaoXu' | 'xiaoHe', expression)`：切换整图并触发 0.6 秒弹跳；不会主动中止正在播放的配音。
- 配音元素 `#voiceAudio`、主播选择 `#voiceAnchor`，配音逻辑在 `talking.js`。
- 自动化若设置音源，先设置 `#voiceAnchor.value` 和 `#voiceAudio.src`，再调用 `playVoice()`；该入口启动 AudioContext 并播放。浏览器首次播放仍需要符合其用户手势规则。
- `pauseVoice()`、`clearVoice()`、`stopAllTalking()` 可停止配音/效果。
- `playVoiceDemo()` 是内置中文音频示例；`playDemo()` 只有字幕和排队表情，并非真实配音。
- 不要将 `startTalking()` 当成可以脱离音频的定时动画入口：当前它调用真实音频播放。
- `DialogueSystem.playNext()` 会调用 `stopAllTalking()`；流水线若同时使用字幕演示队列与配音，会打断音频。集成时避免复用演示队列控制正式播报。
- 图文/视频资讯场景逻辑在 `news-media.js`；保留其素材区、主播和新闻字幕，不需要为本次交接重做布局。

## 验证证据与限制

既有完整素材验收记录在 `outputs/qa/GESTURE_REFRESH_REVIEW.md`，比较图为 `outputs/qa/new-gesture-materials.png` 和 `outputs/qa/five-finger-studio.png`。历史测试结果以该记录为准，本轮没有重跑整个测试集。

本轮用桌面尺寸 1920×1080 的 Edge 自动化逐一点击小禾三个按钮，图片解码成功，加载路径分别为 `anchors/generated/xiaohe-wink.png`、`anchors/gestures-v2/xiaohe-wave.png`、`anchors/gestures-v2/xiaohe-encourage.png`，未捕获页面脚本错误。原生电脑窗口连接超时，无法核对用户当时打开的窗口；用户随后确认看错，无需继续修改。页面等待完整 load 曾超时，改用 DOMContentLoaded 后上述按钮检查可运行；不能将此记录理解为完整页面加载性能通过。

历史 OCR 委派因目录不是 Git 仓库而无法运行，不能报告 OCR 通过。仅检查电脑效果，未做手机验收。

## 协作边界与下一步

本轮仅新增此交接文档。不修改主窗口负责的 `pipeline/`、`config/`、`tests/` 或 `docs/PIPELINE*`，也不覆盖共享演播室文件。当前素材侧无阻塞。下一步由主窗口将真实配音和播报时间轴接入上述现有入口，再对导出成片的声音、字幕、媒体区和人物效果做验收。无需为已关闭的“三个按钮重复”问题返工。
