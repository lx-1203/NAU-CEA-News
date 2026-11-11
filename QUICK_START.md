# 快速开始

1. 下载[完整复刻包](https://github.com/lx-1203/NAU-CEA-News/releases/tag/reuse-pack-v1.0.0)并解压到自己有写权限的 Windows 目录，支持空格和中文。
2. 双击first_run.bat。首次准备Python3.11、Chromium、IndexTTS2工作台和固定模型。建议30GB以上空闲空间及正常工作的NVIDIA驱动。中断后可重试，保留下载缓存。
3. 试听两位主播测试音频；之后使用start.bat。准备下一期用next_episode.bat，已有同日稿件不会被覆盖。
4. 原图与来源按刊期归档；候选/空白稿件均未核实，不能当成成片。完成回源、写稿与审稿后，才规划、配音、渲染、终检。

每次使用先检查架构和skill版本，默认直接连接GitHub公开HTTPS源，不需要自己填写地址。无Python时双击check_updates.bat，仅安装更新检查所需环境；有Python时运行python scripts/check_updates.py --apply。失败会停止，不以本地基线冒充在线检查。

完整复刻包已启用片尾和自动 BGM。每期先按包内 `examples/credits.example.json` 填好 `data/issues/年份/刊期/tasks/credits.json`。正式渲染会按需从公开曲库取歌，带配乐的输出是 `news.mp4`。只更新程序时使用[最新框架与更新包](https://github.com/lx-1203/NAU-CEA-News/releases/latest)，已有素材和本地配置继续沿用。

默认新闻目录：data/issues/YYYY/YYYY-MM-DD。最终视频/播放器/图文在deliverables/current，图片在media/images，音频在audio，任务在tasks。改数据盘只需设置storage.local.json的data_root。

详细步骤见[复用说明](docs/REUSE_GUIDE.md)和[目录与更新机制](docs/ARCHITECTURE.md)。包内skill安装命令：python scripts/install_agent_skill.py --home <助手主目录>。

模型下载、环境安装或GPU合成出错时查看窗口和runtime日志；不要删除其他项目进程或活锁。新电脑全量GPU制作尚需在该电脑实测。
