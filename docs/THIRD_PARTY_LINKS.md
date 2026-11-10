# 复刻所需的官方来源

| 组件 | 地址 | 说明 |
|---|---|---|
| IndexTTS2基础工作台 | https://github.com/lfandrh/indextts2-studio | 固定基础提交bf24477121939a411d31215151a4f7834c1eef6e |
| 长篇台本/时间轴扩展 | https://github.com/Mars-1438/indextts2-longform-workbench | 固定v0.33补丁；它不是独立模型整合包 |
| 长篇补丁下载 | https://github.com/Mars-1438/indextts2-longform-workbench/releases/tag/v0.33 | 安装器核对发布SHA256 |
| 原始IndexTTS项目 | https://github.com/index-tts/index-tts | 模型与软件许可从这里及模型页核对 |
| 主模型 | https://huggingface.co/IndexTeam/IndexTTS-2 | 模型版本、逐文件哈希在reuse-components.json |
| 主模型备用官方渠道 | https://modelscope.cn/models/IndexTeam/IndexTTS-2 | 切换渠道后仍需匹配固定文件哈希 |
| uv | https://github.com/astral-sh/uv/releases | 自动准备Python与环境，下载固定版本并核对SHA |
| GitHub CLI | https://github.com/cli/cli/releases | 在系统钥匙串保存登录，归档时不把凭据写进项目 |
| Git for Windows | https://github.com/git-for-windows/git/releases | 安装器使用固定MinGit到runtime目录 |
| 微软VC运行库 | https://aka.ms/vs/17/release/vc_redist.x64.exe | 缺失时下载并校验微软签名 |
| NVIDIA驱动 | https://www.nvidia.com/Download/index.aspx | 按实际显卡安装驱动，安装器不改驱动 |
| GitHub文件上传API | https://docs.github.com/en/rest/repos/contents | 发布接口使用受支持的Contents API |

本机工作台通常从http://127.0.0.1:7861/longform进入，但端口可能变化。程序读取state_file里的实际URL；别人的电脑不能使用本机localhost地址，必须在自己的电脑启动。日常start.bat会打开正确地址。

模型、工作台补丁、第三方依赖、校徽/社团标识、固定合成参考声和原新闻媒体，各自许可或使用范围不同。包内“合格”指已记录的制作与技术状态，不表示这些内容都获得同一公开再分发许可。新闻稿仓库不上传它们。上游MIT写作参考的LICENSE随agent参考目录保留。
