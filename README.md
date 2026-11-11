# NJAU-CEA 新闻联播

南京农业大学计算机爱好者协会的校园科技新闻项目，提供每日新闻稿和可复用的视频制作流程。

## 下载

| 你想做什么 | 下载入口 | 包含内容 |
| --- | --- | --- |
| **在新电脑复刻节目** | **[完整复刻包](https://github.com/lx-1203/NAU-CEA-News/releases/tag/reuse-pack-v1.0.0)** | 视频工作流、主播表情原图、固定片尾和署名模板、两位主播声音参考、开屏、台标和转场。片尾与自动 BGM 已启用。 |
| 更新已有项目或安装 Codex 技能 | [最新框架与更新包](https://github.com/lx-1203/NAU-CEA-News/releases/latest) | 源码、技能和配置模板。自动更新沿用本地素材与配置。 |
| 单独下载曲库 | [共享音乐包](https://github.com/lx-1203/NAU-CEA-News/releases/tag/music-pack-v1.2.0) | 录音、曲目清单和署名。日更按需取歌，手动下载可获取完整曲库。 |
| 单独导入主播音色 | [双主播音色包](https://github.com/lx-1203/NAU-CEA-News/releases/tag/voice-pack-v1.0.0) | 小序和小禾的固定参考音频、参数和导入脚本。 |

完整复刻包解压后，在 Windows 双击 `first_run.bat` 安装依赖。之后用 `start.bat` 打开演播室，用 `next_episode.bat` 准备下一期。制作新一期时填写当期片尾署名。首次安装需要联网下载 Python、浏览器和语音模型。[快速开始](QUICK_START.md) · [复用说明](docs/REUSE_GUIDE.md)

## 制作与维护

- 了解每期从采集、审稿到配音、渲染和终检的流程。[日更流程](docs/PIPELINE.md) · [编辑规范](docs/EDITORIAL_POLICY.md) · [素材规范](docs/VISUAL_MATERIAL_POLICY.md)
- 查看视频各部件的配置和排查方法。[固定片尾](docs/OUTRO.md) · [自动 BGM](docs/BGM.md) · [主播表情](docs/ANCHOR_ASSET_HANDOFF.md) · [章节进度条](docs/CHAPTER_BAR.md)
- 已有安装可运行 `python scripts/check_updates.py --apply` 更新。也可双击 `check_updates.bat`。框架和技能版本记录在发布清单。[目录与更新机制](docs/ARCHITECTURE.md) · [版本记录](docs/VERSIONING.md)

正式导出的视频在当期 `deliverables/current`，带配乐版为 `news.mp4`，无配乐版为 `news-no-bgm.mp4`。独立素材包附带原始署名与来源，录音、图像和标识保留各自的权利。[新闻稿归档](https://github.com/lx-1203/NAU-CEA-News/tree/main/news)
