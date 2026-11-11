# NJAU-CEA 新闻项目复用说明

在新电脑复刻节目时，下载完整复刻包，解压后运行 `first_run.bat`。日常用 `start.bat`，准备下一期用 `next_episode.bat`。复刻包包含新版主播整图表情、固定声音参考、台标、8 秒开屏、八套栏目转场、固定片尾和署名模板。片尾与自动 BGM 已启用。轮换曲库由独立音乐包提供，正式渲染时按需取歌。[完整复刻包](https://github.com/lx-1203/NAU-CEA-News/releases/tag/reuse-pack-v1.0.0) · [共享音乐包](https://github.com/lx-1203/NAU-CEA-News/releases/tag/music-pack-v1.2.0)

模型和安装工具按config/reuse-components.json固定版本从其上游下载。模型约8.87GB，建议30GB以上磁盘余量；空白Windows全量下载及GPU合成没有在本次架构整理中重新实测。复用包不携带虚拟环境、访问令牌、作者GitHub配置或安装好的模型。

## 路径和数据

默认data/issues/YYYY/YYYY-MM-DD下按editorial、media/images、media/videos、media/evidence、audio、production/runs、deliverables/current、review、tasks分类。目录和命令详见[ARCHITECTURE.md](ARCHITECTURE.md)。本地可设config/storage.local.json；个人路径不会写进代码模板。

刊期是北京时间今天，报道前一完整自然日；六栏目各3条目标18条，证据不足保留缩减版说明，不能拿旧闻补数。新建稿件默认未核实。原文日期证据和图片均使用稿件相对路径；使用前重新校验原文SHA。历史9号、10号归档是学习/审阅材料，不作为今日版复用。

制作新一期时，按包内 `examples/credits.example.json` 填好当期 `tasks/credits.json`，填写经确认的制作人后再渲染。正式成片在 `deliverables/current`，可以打开 `watch.html` 播放。带配乐版为 `news.mp4`，无配乐版为 `news-no-bgm.mp4`。[片尾与署名](OUTRO.md) · [自动 BGM](BGM.md)

历史刊期的便携归档使用 `ISSUE_MANIFEST.json` 校验。需要复查历史制作时，从该刊期的 `editorial` 和 `media` 读取输入，原始制作清单保存在 `review/immutable-originals`。

## 架构和skill更新

architecture/release.json分别记录架构和skill版本。scripts/check_updates.py --apply会实际读取配置源、核对本地完整性、有新版则先下载全部文件核验，再备份升级。失败回滚，冲突保留本地改动；生产入口不可静默跳过。

默认在线源已经配置为 `https://raw.githubusercontent.com/lx-1203/NAU-CEA-News/main/release.json`，不使用包内基线。每次实际获取GitHub清单，有更新则从固定版本tag下载ZIP，整包和全部受管文件SHA匹配后安装；网络失联会明确失败。旧用户若有config/updates.local.json覆盖源，应将其source改成该HTTPS地址。数据、素材和本地配置保留，冲突文件不被强行覆盖。

框架包包含架构、技能和配置模板。复刻包提供生产素材和相应配置，音乐包和音色包可独立下载。线上更新只同步发布清单中的代码、文档与技能；已有安装的素材和本机配置继续沿用。尚未安装 Python 时可双击 `check_updates.bat` 准备更新环境。[框架与更新包](https://github.com/lx-1203/NAU-CEA-News/releases/latest)

维护发布：更新受管清单并递增架构/skill版本，freeze_release.py生成哈希，build_online_release.py生成不可变版本ZIP与根release.json；测试后把同一版本源码及updates/update.zip先推送版本tag，再推送main公开清单。不得覆盖旧tag。

唯一skill源码在skills/nau-cea-daily-video。运行python scripts/install_agent_skill.py --home <助手主目录>后使用；旧版本先备份，存在用户改动则报冲突。每次skill调用先运行自身scripts/check_update.py，它检查项目并同步安装版，不建立第二套生产skill。更换项目位置后重新执行安装命令绑定路径。

## 权限与发布

新闻媒体、音乐、校徽、角色和音色保留各自权利。复刻包中的 `ASSET_CREDITS.md` 记录来源和署名，制作新一期时请按素材规范选择新闻配图。[素材规范](VISUAL_MATERIAL_POLICY.md)

config/github.json默认repository为空。GitHub菜单只归档已审稿件Markdown，不能上传视频、原图、音乐、声音或本地日志；接收者使用自己的仓库与认证。不会携带原作者令牌。

## 已验证与边界

检查应包含源码回归、更新失败/冲突/锁/回滚测试、资产与ZIP清单、在中文空格目录解压后的路径和播放器、原片哈希。新电脑首次安装和完整GPU合成只能由该电脑实际执行后确认；本机现有环境通过不能代替它。
