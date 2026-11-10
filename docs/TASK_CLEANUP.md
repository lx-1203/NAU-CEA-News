# 任务完成后的自动收尾

用户已授权在项目工作完成后自动清理废弃中间产物。先核验当前交付，后清理；失败或在写入时保留恢复资料。Windows仅移入回收站，不永久删除或清空回收站。

正常视频入口 `organize_issues.py --publish-current` 现在包含自动收尾：完成当前版复制、相对资源/文件哈希验证后，更新当前入口，再处理同刊期已登记的生成物及被替代的history。原始媒体、源录音、无BGM混音输入、原稿、源工程、独有QA和当前依赖保留。未知文件或登记与当前内容不一致时保留并记明原因，不能凭新旧编号删除。

成功渲染写cleanup-candidates.json，清单自身哈希绑定manifest.json。登记的是本渲染器实际生成、且在最终化后可以重建或已被验证副本替代的文件；不把任意run目录全当垃圾。缺少成功渲染登记的失败目录由任务负责人核实替代和恢复依赖后，走通用任务清理入口，不自动扫描删除。

每期 tasks/cleanup-queue.json 保留已登记队列，cleanup-state.json、cleanup-log.jsonl记录计划与逐文件结果。清理中断可重跑，已经有成功回收回执的同一文件不重复操作。任务状态complete或pending_cleanup分别表示收尾完成或仍有未解决的清理错误；当前最终版即使有效，也不能将清理失败冒称任务全部闭环。

原始render manifest作为历史构建记录保持字节不变；被退休的文件见清理日志，它不再意味着原run仍是完整可重跑包。需要重跑该历史轮次时，应先从回收站恢复列出的文件。current及其finalization清单仍必须完整有效。

架构/打包任务的通用入口：

```powershell
python scripts/cleanup_completed_task.py --scope <本任务输出根> --artifact-root <最终包根> --final-manifest <最终包清单> --retire <废弃版本路径>
```

retire可重复。只枚举明确列出的退休组，不沿目录联接。先验证最终清单的每个文件，再快照候选；候选变化、保护文件变化、渲染活锁或回收失败时不强删。必须是本任务已确认废弃的产物；共享目录、个人文件和其他日期不属于默认授权范围。最终清单可为BUNDLE_MANIFEST.json、FRAMEWORK_MANIFEST.json或ISSUE_MANIFEST.json，files支持SHA字符串或带sha256/bytes的对象。

计数分别记录移走的文件和字节数；回收站未清空，实际磁盘释放量不推测。空的历史容器可以留下，不能为了移除目录而递归清空混有原件或证据的目录。
