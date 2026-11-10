# NJAU-CEA 固定双主播音色包 1.0.0

南京农业大学计算机爱好者协会（Computer Enthusiasts Association）。固定音色：**小序自然男童 boy-v2**、**小禾自然女童 girl-v2**。包中两份 WAV 是现有生产所用的冻结参考原件，不需要重新挑选音色或在线克隆。

## 一键启用

1. 安装好 [IndexTTS2 Studio](https://github.com/lfandrh/indextts2-studio) 及 [Longform Workbench](https://github.com/Mars-1438/indextts2-longform-workbench)。本包只装音色，不携带模型、Python环境或显卡驱动。
2. 下载本独立音色 ZIP，**完整解压**到有写权限的位置。支持中文、空格目录，不要在压缩包里双击。
3. 双击 **start.bat**。若未自动找到工作台，第一次选中包含 `server.py` 的工作台根文件夹。之后会记住位置。
4. 脚本校验包和音频，导入两预设、启动已有工作台，并核对服务端参数和原始 WAV 后打开页面。在页面的音色预设中选择：
   - `NJAU-CEA-xiaoXu-boy-v2`：小序男童。
   - `NJAU-CEA-xiaoHe-girl-v2`：小禾女童。

已有同名且同字节预设会直接复用；同名内容不同时停止，**不覆盖你的预设**。请在工作台先重命名自己的冲突预设后再运行。启动不合成语音，不加载推理模型；正式试听合成仍需模型和可用显存。

冷启动兼容Windows自带PowerShell5.1，直接使用工作台已安装的Python和`server.py`，自动选择空闲端口，不依赖原作者的启动脚本。优先复用同一工作台状态文件中的在线服务。若你自行启动了服务、没有状态文件，可先用`-NoLaunch`导入，再刷新已打开的工作台页面。

也可以把音色包放在工作台旁边：二者同目录、工作台名为 `IndexTTS2-Studio` 时能自动识别。命令行方式：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\enable.ps1 -WorkbenchRoot "E:\音频工作台\IndexTTS2-Studio"
# 只导入，不启动、不打开浏览器：
powershell -NoProfile -ExecutionPolicy Bypass -File .\enable.ps1 -WorkbenchRoot "E:\音频工作台\IndexTTS2-Studio" -NoLaunch
# 只校验音色包：
powershell -NoProfile -ExecutionPolicy Bypass -File .\enable.ps1 -VerifyOnly
```

## 手动导入与工作台兼容

适配已实测的 IndexTTS2 Studio 原生 `outputs/presets/<name>/preset.json + prompt.wav` 结构。把包内 `presets` 下的两个子文件夹复制到工作台 `outputs/presets`，再刷新页面即可。不要覆盖自己的同名预设；参考 WAV 和 JSON 必须一起复制。

如果你的其他版本只允许网页导入参考音频：分别上传相应 `prompt.wav`，按 `voice-profile.json` 设置情绪、分句和高级参数，保存为同名预设。参数不兼容或缺少原生预设接口时，脚本会停止并提示；不会假装导入成功。参考模型和上游版本见 `COMPATIBILITY.json`。

## 固定参数

两位主播使用相同合成参数，音色区别来自各自参考 WAV：

| 项目 | 值 |
|---|---|
| 情绪模式 `emo_control_method` | 2（向量） |
| 情绪向量 | `[0,0,0,0,0,0,0,0.65]` |
| 情绪权重 | 0.65 |
| 随机情绪 | false |
| 分句上限 `max_text_tokens_per_segment` | 80 |
| 采样 `do_sample` / top_p / top_k | true / 0.8 / 30 |
| temperature / num_beams | 0.8 / 3 |
| length_penalty / repetition_penalty | 0 / 10 |
| max_mel_tokens / interval_silence | 1500 / 200毫秒 |
| 项目合成速率 `rate` | 1.0；随后按实测语速处理 |

原始预设和参考 WAV 的 SHA256 在 `voice-profile.json`、完整文件校验在 `PACKAGE_MANIFEST.json`。导入后不依赖音色包原来的磁盘位置；参考音频已复制到工作台内部。`runtime` 只记录接收者本机路径与启用回执，不包含在发布包中。

## 语速和复刻边界

项目要求两主播正文实测 **280–300字/分钟**，普通句约295，数字/术语密集句约285。它是**合成后的不变调校准规则**，不等于工作台里选了 `rate=1.0` 就自动达标，也不是原生预设支持的 CPM 字段。

完整规则随 `voice-profile.json` 保存。沿用新闻项目时使用 `pipeline/pacing.py` 校准并按实际音频时长重排字幕；只用工作台时需导出后测量并用不变调速度调整。目标秒数约为“实际读出的字数×60÷目标字速”，数字应按读出来的汉字计数，英文术语需提供实际读音；句尾留白也计入正文总时长。调整量超出0.75–1.6倍时重新合成，不硬压到目标。

同模型、同参考、同参数可复现同一音色方向。因为 `do_sample=true` 且硬件/运行环境可能不同，每次停顿、细节和文件字节不保证完全一致。包内保留参考来源说明；未声称任何真人声音授权或逐字口型能力。

## 下载与版本

本包的公开发布由用户于2026-11-10明确授权，只包含这两份冻结参考及配套工具和说明。公共新闻框架仍不自动包含其他媒体、角色、音乐或模型。

[固定版本下载](https://github.com/lx-1203/NAU-CEA-News/releases/tag/voice-pack-v1.0.0)。不要把未校验的第三方同名音色当成本包。收到错误时保留窗口提示；首次安装模型/驱动仍由工作台自己的安装流程负责。
