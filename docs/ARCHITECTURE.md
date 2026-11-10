# NJAU-CEA 新闻项目架构 1.1.2

下载整个复用包后解压到任意 Windows 目录；程序自动定位自己的根目录，不依赖原作者的 D、F 盘。双击 first_run.bat 首次安装，start.bat 日常启动，next_episode.bat 准备新一期。角色、固定音色及合格共享素材随包提供；模型按固定来源另行下载。

```text
NJAU-CEA-News/
  architecture/                架构/skill版本、受管文件哈希、附带发布基线
  skills/nau-cea-daily-video/  唯一新闻skill入口及引用资料
  pipeline/ scripts/ tests/   生产代码、命令入口与行为测试
  config/                     默认配置；*.local.json只属于本机
  assets/                     共享角色、演播室、LOGO、音色、转场
  docs/                       规范、复用说明、当前待办
  data/                       默认数据根，可配置到别的盘
    issues/2026/
      2026-11-09/
      2026-11-10/
        editorial/            edition.json、候选、审稿
        media/images/         当期原始图片
        media/videos/         当期原始视频
        media/evidence/       原文、日期、许可证等存证
        audio/source/         原始配音/当期音乐
        audio/cues/           处理后逐句音频
        production/runs/      分轮次制作的中间文件
        deliverables/current/ 当前成片、播放器、图文、字幕、章节
        review/               当期核验和历史原件清单
        tasks/status.json     当期任务状态
  runtime/ .venv/ .tools/     本机安装环境，不装进源码更新
```

本机数据根：config/storage.local.json 的 data_root。别人下载默认项目内 data；可以复制 storage.example.json 为 storage.local.json 后改路径，或用 NJAU_CEA_DATA_ROOT 环境变量。相对路径以项目根为基准。请勿将本机local配置、令牌、环境目录纳入分发包。

新刊期通过 pipeline.storage.issue_paths 建目录。collect/new/plan/render/desktop统一调用该接口；下载原图时用 register_media 或 organize_issues.py --media，按刊期即时归类，重名且内容不同自动加哈希后缀。图片来源、资料画面用途和SHA仍必须记录；归类不代表审核或获准公开发布。证据截图仅作核验，不是合格新闻配图。禁止用SVG、Canvas、Pillow等自行绘制图片或LOGO替代所需原图。

render先写production/runs和audio/cues/轮次，状态为待终检；不会把未经终检的新片冒称当前最终版。终检通过后使用 `organize_issues.py --date YYYY-MM-DD --pointer <该轮交付指针JSON> --publish-current` 将配套交付归入当期deliverables/current，保留已有稿件和任务；旧current保存在同级history目录。该操作保存独立finalization清单，之后可按依赖清理历史中间版。9号、10号的历史封存目录不在原地继续生产，若重制应选新工作数据根或独立导出路径。

历史最终片以原哈希保留，分类归档是二进制相同的副本和独立相对路径清单；原始制作清单只作为历史证据保留。旧清单不会被改写来伪造“当前源码仍一致”。原片仍可播放，不代表其旧源码满足后来的新要求。新制作轮次与当前交付分别存放，清理按实际依赖进行。

## 使用前更新与自检

架构版本和skill版本分别存 architecture/release.json。运行 scripts/check_updates.py --apply，或通过启动入口/skill入口执行。每次实际读取发布源，比较版本和文件SHA；相同版本仍检查受管代码完整性。新版本全部校验完成后才备份并替换，失败回滚，不覆盖本地修改。更新中的进程必须重启后使用新源码。活跃渲染锁或更新锁存在时不强行清理。

更新范围只有清单明确列出的程序、共享接口和skill，不能包含data、outputs、runtime、本地配置或按日期产生的文档。模型/第三方依赖固定版本，不随架构升级偷偷重装。新版本需要额外数据迁移时另写并验收迁移，不把个人文件作为源码覆盖。

架构升级与渲染持有同一协调锁；渲染启动时再核对检查回执与版本、文件哈希。检查后恰逢升级会要求新进程重试，不能边渲染边替换程序。

发布源支持HTTPS release.json或file URI、本项目内相对路径。发布目录必须同时提供清单列出的文件，以相同相对目录排列。`python scripts/publish_local_release.py --output <空发布目录>` 会校验后生成发布目录。

维护者先修改受管文件；新增受管源码时同步architecture/managed-files.json，然后运行 `python scripts/freeze_release.py --architecture-version 1.1.1 --skill-version 1.1.0` 生成新哈希。skill改变时递增skill-version。禁止同版本变更文件哈希；生成清单后运行build_online_release.py生成固定版本ZIP与根release.json，再完成测试与发布；推送main清单和对应不可变版本tag。先发布tag中的ZIP，再发布新的main清单，最后以匿名下载验证。

默认公开更新源：`https://raw.githubusercontent.com/lx-1203/NAU-CEA-News/main/release.json`。每次启动实际读取该HTTPS清单；有新版时下载固定版本tag下的updates/update.zip，先核对整包SHA256、ZIP成员范围与每个受管文件SHA，全部通过后事务安装。网络失败直接报错，不退回本地基线。config/updates.local.json仅用于明确选择其他可信镜像；旧包若存在本地基线覆盖配置，需要将source改为上述在线地址。

GitHub仓库同时提供架构与skill源码，以及公共框架ZIP。公共包不上传新闻媒体、音乐、音色、人物/LOGO位图、模型和本机配置。在线检查和skill安装可独立使用；整期生产仍需合法提供自己的共享素材，或在有权限的前提下使用既有本地完整素材包。默认公开配置未启用未经提供的开屏。

配套skill的唯一源码为 skills/nau-cea-daily-video。`python scripts/install_agent_skill.py --home <助手主目录>` 安装/同步到该助手的skills目录，旧版先备份；本地被改动则保留并报冲突。已安装skill每次使用先运行自身scripts/check_update.py，再从项目同步。更换项目路径后再次执行安装命令即可重绑。

## 任务分类与日常命令

docs/TODO.md仅保留未关闭事项，详细证据归当期review，状态归tasks/status.json。完成事实核验、配音、渲染、终检后分别更新任务状态；候选、空模板或技术通过均不冒充可发布成片。

```powershell
python scripts/check_updates.py --apply
python -m pipeline.portable new --date 2026-11-11 --keep-existing
python -m pipeline.run collect --date 2026-11-11
python -m pipeline.run plan --edition data/issues/2026/2026-11-11/editorial/edition.json
python -m pipeline.run render --edition data/issues/2026/2026-11-11/editorial/edition.json
python scripts/organize_issues.py --date 2026-11-11 --media C:/Downloads/photo.jpg
```

以上data命令使用默认数据根；本机另配数据盘时以issue_paths返回的路径为准。日期是刊期，报道覆盖前一完整北京时间自然日。历史复刻需明确archive例外，不把9号/10号样例当当天新闻。
