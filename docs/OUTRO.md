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
