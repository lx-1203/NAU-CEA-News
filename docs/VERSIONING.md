# 版本与变更记录

自2026-11-10起，每次更新必须在交付前同步更新对应版本号、变更记录和实际发布包；本机生效的skill也在此范围内。不能等用户提醒，不能仅在聊天中承诺。

## 版本规则

- 项目受管代码、配置模板或规范发生变化，递增`architecture_version`；skill入口、规则、引用资源或脚本变化，另递增`skill_version`。权威清单为`architecture/release.json`。skill版本还需与唯一入口`skills/nau-cea-daily-video/SKILL.md`的metadata.version及正文一致。
- 修复、文档和规范小改动递增PATCH；兼容的新功能递增MINOR；不兼容变更递增MAJOR。未改变的独立组件保留原版本。
- 独立音色包使用自身版本：同步更新voice-profile、PACKAGE_MANIFEST、包名和GitHub release/tag，重新打包并验SHA256。固定参考音频或参数未经用户要求不变；版本升级不代表重新选声。
- 新一期新闻以刊期日期区分；同一期每次交付新版视频递增修订号，例如`2026-11-10-r2`，保存与成片哈希绑定的交付清单。不能覆盖旧版后仍声称原版本、原审查有效。
- 已交付的版本、tag及下载包内容不可变。改动后发布新版本；相同内容的校验、重复下载或幂等导入不算更新。

## 发布核对

1. 记录本次变更，递增实际受影响的组件版本。更新受管文件列表；新增源码、规范、测试必须纳入。
2. 运行`python scripts/freeze_release.py --architecture-version <新项目版本> --skill-version <当前或新skill版本>`。受管文件变化而项目版本未升、skill变化而skill版本未升均拒绝生成清单。
3. 运行`python scripts/build_online_release.py`；需要完整框架下载包时再运行`build_framework_package.py`。核对根release.json、架构清单、skill版本、ZIP实际内容和SHA256。
4. 运行相关测试与终检后发布新不可变tag和对应更新ZIP，再更新main发布清单；同步安装本机skill。匿名读取线上清单、下载包并实际校验。同步失败要写明未更新，不能冒称本机和GitHub已一致。

## 变更记录

### 项目1.2.1 / skill1.2.1 — 2026-11-10

- 固化每次更新同步版本及变更记录的要求，覆盖项目、skill、独立音色包和成片修订。
- 发布冻结器分别检查项目和skill是否递增；skill资源删除也纳入比较；检查失败保留旧清单。
- skill增加可见版本信息；维护唯一入口，同步已安装副本。
- 独立音色包仍为1.0.0，原参考音频、合成参数和新闻配音未变。

### 项目1.2.0 / skill1.2.0 — 2026-11-10

已发布基线：任务完成后按实际依赖自动回收废弃中间产物，保留原件、当前交付和唯一证据；清理状态持久记录。详细规则见TASK_CLEANUP.md。
