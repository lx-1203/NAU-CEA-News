# NJAU-CEA 共享音乐包 v1.0.0

收录此前实际使用的三首原始MP3：《ALisa - 盛夏》《纯音乐 - 起风了（钢琴版）》及Kevin MacLeod的《News Theme》。原文件未转码；逐曲SHA256、时长、来源、历史用途与可复用混音参数见MUSIC_MANIFEST.json。

下载：[NJAU-CEA-Music-Pack-v1.0.0.zip](https://github.com/lx-1203/NAU-CEA-News/releases/download/music-pack-v1.0.0/NJAU-CEA-Music-Pack-v1.0.0.zip)。校验文件与曲目清单在同一Release。

使用：完整解压，把包内assets目录合并到新闻项目根目录。音乐位于assets/audio/music；该目录的MUSIC_MANIFEST.json是共享音乐清单。遇到同名文件时先核对SHA256，内容不同则保留双方，不直接覆盖。

本组件版本独立为1.0.0；框架与skill仍为1.2.1。它是可选音乐资产包，搭配既有框架与其他素材使用。共享入库后各期按需选择，历史混音参数仅作模板；不会自动将任何歌曲设为每日默认配乐。

三首文件均完成完整音频解码和原始SHA核对。权利与署名见RIGHTS.md和CREDITS.txt；原曲和录音不因加入本包而统一成为开源音乐。
