# IndexTTS2本地工作台接入

本项目采用固定双主播参考与串行批量合成。实际路径和参数从 `config/pipeline.json` 的 `speech.workbench` 读取。克隆仓库即可取得两位主播的参考音频。安装后先校验 SHA256 并试听。[参考音频目录](../assets/voices/)

在仓库目录运行 `first_run.bat`，安装程序先校验制作素材，再准备 `runtime/IndexTTS2-Studio`、`runtime/client-config`、固定版本依赖及模型。依赖地址与校验值记录在 `config/reuse-components.json`。[首次安装](../QUICK_START.md) · [第三方来源与许可](THIRD_PARTY_LINKS.md)

工作台实际端口来自配置state_file中的url字段；有自己的启动器时通过start_script启动，不固定端口、不结束其他项目进程。客户端路径由client字段提供，新闻程序沿用segments预览、batch串行合成与manifest验证，不额外部署远程服务。

两位主播：小序自然男童boy-v2，小禾自然女童girl-v2。用户纠正优先于历史命名。固定参考SHA、情绪参数、基础rate与语速策略以本机配置为准；拒绝缺句、截断或哈希变化，失败时保留日志和已有成片。

新一期原配音存data/issues/年份/刊期/audio/source/轮次，处理配音存audio/cues/轮次；任务、读音预览、工作台结果和来源清单归production/runs，日期任务状态归tasks。失败可按指纹重试，禁止并发抢GPU。正文实际280–300字/分钟，使用不变调处理，不能只用统一倍率替代测量。

启动入口scripts/start_workbench.ps1；完整安装scripts/bootstrap.ps1；生成前先检查架构和skill在线版本。程序读取当前配置，不把这份说明里的历史测试当成本机已完成GPU验收。安装日志与模型体检应保存在本机runtime或日期review，不上传GitHub。
