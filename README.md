# NJAU-CEA 新闻联播

南京农业大学计算机爱好者协会的校园科技新闻项目，提供每日新闻稿和可复用的视频制作流程。

## 获取项目

在装有 Git 的 Windows 电脑上运行：

```powershell
git clone --depth 1 https://github.com/lx-1203/NAU-CEA-News.git
```

进入克隆得到的 `NAU-CEA-News` 目录，双击 `first_run.bat` 安装依赖。之后用 `start.bat` 打开演播室，用 `next_episode.bat` 准备下一期。新安装默认启用开屏、固定片尾和自动 BGM。制作新一期时填写当期片尾署名。[快速开始](QUICK_START.md) · [复用说明](docs/REUSE_GUIDE.md)

## 素材目录

| 素材 | 仓库目录 |
| --- | --- |
| 两位主播的表情与姿态原图 | [assets/characters](assets/characters/) |
| 小序与小禾的固定参考音频 | [assets/voices](assets/voices/) |
| 固定片尾、校歌曲段和署名模板 | [assets/outro](assets/outro/) |
| 8 秒开屏与配乐署名 | [assets/opening](assets/opening/) |
| 台标和演播室标识 | [assets/branding](assets/branding/) |
| 栏目转场及预览 | [assets/transitions](assets/transitions/) |
| BGM 单曲、曲目清单和署名 | [assets/audio/music](assets/audio/music/) |

单独取用素材时，进入相应目录选择文件。素材来源、署名和适用范围见[素材索引](assets/README.md)。

## 制作与维护

- 了解每期从采集、审稿到配音、渲染和终检的流程。[日更流程](docs/PIPELINE.md) · [编辑规范](docs/EDITORIAL_POLICY.md) · [素材规范](docs/VISUAL_MATERIAL_POLICY.md)
- 查看视频各部件的配置和排查方法。[固定片尾](docs/OUTRO.md) · [自动 BGM](docs/BGM.md) · [主播表情](docs/ANCHOR_ASSET_HANDOFF.md) · [章节进度条](docs/CHAPTER_BAR.md)
- 从 Git 克隆的项目可在启动前运行 `git pull --ff-only`，同步源码和素材。旧安装仍可用 `check_updates.bat` 更新程序。[更新机制](docs/ARCHITECTURE.md) · [版本记录](docs/VERSIONING.md)

正式成片在当期 `deliverables/current`，带配乐版为 `news.mp4`，无配乐版为 `news-no-bgm.mp4`。[新闻稿归档](news/)
