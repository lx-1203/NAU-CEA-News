# NJAU-CEA 新闻联播

南京农业大学计算机爱好者协会（Computer Enthusiasts Association）校园科技每日新闻项目。节目品牌与LOGO为大写NJAU-CEA；开场首先说明“这里是南京农业大学计算机爱好者协会。”

这是可迁移的源码与工作流程，下载复用请使用完整版本包，保留目录结构。首次双击 first_run.bat，日常 start.bat，下一期 next_episode.bat。全新电脑会下载固定版本的Python、依赖与IndexTTS2模型；不是预装模型的离线包。

## 从这里开始

[下载公共架构与skill包](https://github.com/lx-1203/NAU-CEA-News/releases/latest)。公共包不包含生产媒体；已有授权本地素材包可搭配使用。

- [快速开始](QUICK_START.md)：安装、启动、下一期。
- [架构与目录](docs/ARCHITECTURE.md)：日期分类、任务分类、架构/skill使用前更新。
- [复用说明](docs/REUSE_GUIDE.md)：新电脑、配置、分发范围与验证边界。
- [编辑规范](docs/EDITORIAL_POLICY.md)与[素材规范](docs/VISUAL_MATERIAL_POLICY.md)：日期、事实和原始媒体准入。
- [当前待办](docs/TODO.md)：仅保留尚未关闭事项。
- [自动收尾](docs/TASK_CLEANUP.md)：工作完成并核验最终版后，回收明确废弃的中间产物，保留原件和依赖。
- [视频章节进度条](docs/CHAPTER_BAR.md)：日更自动合成底栏，也可给已有成片添加。

程序为pipeline/scripts，配置为config，共享角色/声音/演播室/LOGO/转场为assets。每期数据默认在data/issues/YYYY/YYYY-MM-DD，分editorial、media、audio、production、deliverables、review、tasks。另用数据盘时配置config/storage.local.json，不改源码；环境和个人配置不进入复用包。

唯一配套skill：skills/nau-cea-daily-video。全局安装使用python scripts/install_agent_skill.py --home <助手主目录>，安装前保留旧版，后续每次调用自检并同步项目版。

架构和skill版本见architecture/release.json。每次更新都必须递增对应版本，skill同步更新；规则与变更记录见[docs/VERSIONING.md](docs/VERSIONING.md)。默认在线源是 https://raw.githubusercontent.com/lx-1203/NAU-CEA-News/main/release.json ，每次使用都会实际检查，下载固定版本更新包并核验后备份安装。网络失败或本地冲突会停止，不回退到本地基线。已有Python可运行 `python scripts/check_updates.py --apply`；没有Python可双击check_updates.bat，它只准备更新所需环境，不下载语音模型。

GitHub公开发布的是架构、skill和配置模板；没有新闻图片、音乐、音色或人物/LOGO位图。完整生产需提供合法共享素材；公共框架包可独立更新和安装skill，full setup在素材缺失时会明确停止。解压既有完整本地素材包的用户也可直接升级代码，数据和素材不被覆盖。

新闻稿归档保留在[news目录](news/)，不因架构发布删除。

本项目不会因复制复用包获得第三方新闻图片、音乐、校徽、人物或声音的公开再分发许可。视频保持待发布，GitHub归档功能仅处理已审核新闻稿，默认不配置他人的仓库。

## 自动 BGM

架构 1.3.0 起每期自动更新曲库元数据、按轮选取未用歌曲、临时下载与混音，用后删除下载缓存，只保留小型使用记录。全部用过后重开一轮；失败不计数，同一期重导出沿用。见 [BGM 工具说明](docs/BGM.md)。音乐录音为独立组件，框架包不携带整库。


双主播表演编排与素材安装见[主播素材交接](docs/ANCHOR_ASSET_HANDOFF.md)。平静、开心、讲解、思考每位主播各三套，制作时按句意轮换。
