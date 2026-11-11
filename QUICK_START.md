# 快速开始

1. 在有写权限的 Windows 目录，用 Git 克隆项目：

   ```powershell
   git clone --depth 1 https://github.com/lx-1203/NAU-CEA-News.git
   ```

2. 进入 `NAU-CEA-News`，双击 `first_run.bat`。首次安装会下载 Python、Chromium、IndexTTS2 工作台和固定模型，建议预留 30 GB 以上空间并准备可用的 NVIDIA 驱动。
3. 试听两位主播测试音频。之后使用 `start.bat` 启动演播室，准备下一期用 `next_episode.bat`。
4. 按当期日期归档稿件、原图和来源，完成回源与审稿，再配音、渲染和终检。[日更流程](docs/PIPELINE.md)

片尾、开屏和自动 BGM 在新安装中默认启用。渲染前按片尾说明填写当期的 `tasks/credits.json`。正式渲染先使用本地已校验的 BGM，缺少本地单曲时下载该文件。输出 `news.mp4` 为带配乐版。[片尾与署名](docs/OUTRO.md) · [自动 BGM](docs/BGM.md)

默认数据目录为 `data/issues/YYYY/YYYY-MM-DD`。视频、播放器和图文在当期 `deliverables/current`，图片在 `media/images`，音频在 `audio`，任务在 `tasks`。如需换盘，在 `config/storage.local.json` 中设置 `data_root`。

已有安装只更新程序时，可双击 `check_updates.bat` 或运行 `python scripts/check_updates.py --apply`。希望从新版默认素材与配置开始的用户可按上面的步骤克隆到新目录。[复用说明](docs/REUSE_GUIDE.md) · [更新机制](docs/ARCHITECTURE.md)

安装或 GPU 合成出错时，查看启动窗口的提示和 `runtime` 中的日志。
