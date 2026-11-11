# 固定片尾与每期署名

每日制作入口为 `python -m pipeline.run render --edition <稿件.json>`。本机配置启用下列选项后，正式渲染会在新版主播表情编排完成后接入已批准片尾。

```json
{
  "outro": {"enabled": true, "package": "assets/outro"},
  "transitions": {"library": "assets/transitions/campus-ip-sweep-v4/library.json"}
}
```

`outro.package` 指向授权片尾目录。工具核对 `CURRENT.json`、`MANIFEST.json`、署名模板、双主播原声和校歌版源视频，原媒体可存于独立素材库。版本 1.4.1 片尾为 24.4 秒，正式成片按节目帧率输出。转场库也可指向现有共享目录。

每期在数据根 `issues/年份/刊期/tasks/credits.json` 记录用户确认的署名。

```json
{"edition_date":"2026-11-11","producer":"星迹","confirmed_by_user":true,"producer_only":true}
```

默认制片人从「星迹、Codex」开始，追加当期制作人并去重。用户明确只显示当期署名时设置 `producer_only=true`。参演人员为「楠小禾、秾小序」。缺少经确认的当期署名时，提示补齐该文件。

固定片尾替换原有两句通用收尾，带入固定双主播告别、署名和校歌曲段。正文自动轮换 BGM 在片尾前淡出。无配乐版复用相同画面、章节和口播，尾段使用原声。播放器提供「片尾与署名」章节，字幕随实际时间线偏移。

复用已有配音时加 `--audio-manifest <配音清单.json>`。旧清单中的通用收尾条目会被当期片尾替换，正文每句仍按源文件 SHA256 校验。成片记录 `outro-receipt.json` 和 `bgm-receipt.json`，归档时同步保留。

## 在 Shotcut 里编辑片尾

克隆仓库，在 [Shotcut](https://shotcut.org/) 中打开 [outro-edit.mlt](../assets/outro/outro-edit.mlt)。画面、两位主播的告别人声、校歌和三张署名卡各自独立，可以移动、裁切、替换或静音。工程是 1920×1080、60 帧、24.4 秒，链接使用仓库内相对路径。保留 `assets/outro` 的目录结构，避免素材掉线。

署名卡是带透明背景的图层。改字或改样式时，先在素材目录的副本中修改 `source/credits.json` 或 `source/credits.html`。在已安装 Python、Playwright 和 Edge 的项目根目录运行 `python scripts/export_outro_project.py --outro <素材副本路径>`，即可更新透明署名卡和默认工程。重新生成会重置工程时间线，请先另存手工剪辑版。

双主播动画在剪辑工程里使用已批准的画面底片。需要改人物位置、表情图、字幕样式或背景时，可编辑 [原画面 HTML 源码](../assets/outro/editable/visual/outro.html)。源码中的 `drawFrame(帧号)` 可预览指定帧。原画面源码、图片和音频分开保存在仓库中。

日更自动渲染仍读取批准的素材目录和当期 `tasks/credits.json`。自行剪辑的工程和片尾版本可在 Shotcut 中独立导出。
