# IndexTTS2本地工作台接入

本项目采用固定双主播参考与串行批量合成。实际路径和参数读取config/pipeline.json中的speech.workbench，不能沿用制作机盘符。公开框架不包含音色录音或模型；使用者应合法提供参考音频，校验SHA并先试听。

下载完整获授权的本地素材包后，first_run.bat准备runtime/IndexTTS2-Studio、runtime/client-config、固定版本依赖及模型；源码、模型地址与SHA在config/reuse-components.json，许可见THIRD_PARTY_LINKS.md。公共框架缺少素材清单时不会自动下载大量模型。

工作台实际端口来自配置state_file中的url字段；有自己的启动器时通过start_script启动，不固定端口、不结束其他项目进程。客户端路径由client字段提供，新闻程序沿用segments预览、batch串行合成与manifest验证，不额外部署远程服务。

两位主播：小序自然男童boy-v2，小禾自然女童girl-v2。用户纠正优先于历史命名。固定参考SHA、情绪参数、基础rate与语速策略以本机配置为准；拒绝缺句、截断或哈希变化，失败时保留日志和已有成片。

新一期原配音存data/issues/年份/刊期/audio/source/轮次，处理配音存audio/cues/轮次；任务、读音预览、工作台结果和来源清单归production/runs，日期任务状态归tasks。失败可按指纹重试，禁止并发抢GPU。正文实际280–300字/分钟，使用不变调处理，不能只用统一倍率替代测量。

启动入口scripts/start_workbench.ps1；完整安装scripts/bootstrap.ps1；生成前先检查架构和skill在线版本。程序读取当前配置，不把这份说明里的历史测试当成本机已完成GPU验收。安装日志与模型体检应保存在本机runtime或日期review，不上传GitHub。
