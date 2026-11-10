# 每日新闻稿GitHub归档

用户于2026-11-09授权每日上传新闻稿，并指定在GitHub账户lx-1203下创建仓库。当前仓库为https://github.com/lx-1203/NAU-CEA-News，公开，仅归档新闻稿与来源；本次没有获得自动发布视频、第三方媒体或模型音色的范围扩展。

编辑完成后，在相同日期目录提供editorial-review.json。以下字段必须来自实际审查：

```json
{
  "status": "passed",
  "edition_sha256": "当前edition.json的实际SHA256",
  "facts_checked": true,
  "date_checked": true,
  "dedup_checked": true,
  "narration_checked": true
}
```

程序还会重新验证edition字段与日期证据。审稿状态或SHA不符即拒绝上传。发布用Markdown从白名单字段生成：标题、摘要、读者关联、口播、原始来源与时间。内部verification_note、本地路径、原文缓存、声音参考、新闻图片/视频和日志不上传。

```powershell
python -m pipeline.run archive --edition outputs/daily/2026-11-10/edition.json --review outputs/daily/2026-11-10/editorial-review.json
python -m pipeline.run archive --retry-pending
```

config/github.json填写repository（owner/repo），branch可留空使用默认分支。凭据优先GITHUB_TOKEN环境变量，其次项目内或PATH里的GitHub CLI系统登录。复用包提供gh，不需要在聊天里提供令牌。令牌、HTTP请求头与异常对象不会写进发布回执。

文件位置news/YYYY/MM/YYYY-MM-DD.md。相同内容幂等跳过，更新使用GitHub当前文件SHA避免无条件覆盖；冲突或网络失败保留本地稿和receipt，退出码2表示未完成上传。回执只有拿到远端成功响应后才标uploaded。目标必须是已配置的公开仓库。

18条新规范生效前已有的8条历史试运行稿，归档时必须在publication_note说明版本和不足，不称为完整18条日报。新一期仍按六栏各3条执行。视频审阅暂停不妨碍已完成审查的文本稿归档。
# 架构发布与新闻归档的范围

用户已单独授权将架构、配套skill、配置模板和更新包发布到本仓库。此范围不包含新闻原图、音乐、音色、模型或本机配置。日常自动新闻归档仍仅写news目录内已审Markdown，不因此获得自动发布素材或升级代码的权限。公开架构版本由维护者显式制作、验收并发布。

