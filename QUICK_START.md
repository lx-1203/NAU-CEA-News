# 快速开始

1. 将完整ZIP解压到自己有写权限的Windows目录，支持空格和中文。不要直接在压缩包内运行。
2. 双击first_run.bat。首次准备Python3.11、Chromium、IndexTTS2工作台和固定模型。建议30GB以上空闲空间及正常工作的NVIDIA驱动。中断后可重试，保留下载缓存。
3. 试听两位主播测试音频；之后使用start.bat。准备下一期用next_episode.bat，已有同日稿件不会被覆盖。
4. 原图与来源按刊期归档；候选/空白稿件均未核实，不能当成成片。完成回源、写稿与审稿后，才规划、配音、渲染、终检。

每次使用先检查架构和skill版本，默认直接连接GitHub公开HTTPS源，不需要自己填写地址。无Python时双击check_updates.bat，仅安装更新检查所需环境；有Python时运行python scripts/check_updates.py --apply。失败会停止，不以本地基线冒充在线检查。

公共下载是架构/skill包，不含新闻图片、音乐、音色与人物/LOGO位图；完整生产需要合法素材。first_run.bat会在缺少素材清单时明确停止，不先下载大量模型。已有本地完整素材包的用户可升级程序并保留原素材。

默认新闻目录：data/issues/YYYY/YYYY-MM-DD。最终视频/播放器/图文在deliverables/current，图片在media/images，音频在audio，任务在tasks。改数据盘只需设置storage.local.json的data_root。

详细步骤见[复用说明](docs/REUSE_GUIDE.md)和[目录与更新机制](docs/ARCHITECTURE.md)。包内skill安装命令：python scripts/install_agent_skill.py --home <助手主目录>。

模型下载、环境安装或GPU合成出错时查看窗口和runtime日志；不要删除其他项目进程或活锁。新电脑全量GPU制作尚需在该电脑实测。
