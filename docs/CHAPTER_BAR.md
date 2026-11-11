# 视频底部章节进度条

从架构 1.6.0 开始，常规日更 `render` 默认将进度条合成到成片和无配乐版。画面等比例缩放，给底栏留出独立空间，保留原来的台标、字幕和滚动快讯。橙色按播放进度从左往右推进。

分段读取 `chapters.json`，它来自实际完成的时间线，已经计入开屏、目录、转场和片尾。底栏显示开场、目录、实际出现的栏目与片尾，长度与播放时间成比例。网页播放器和 MP4 的内嵌章节仍保留逐条新闻跳转。

已有成片可以单独补制。在已经准备 Python 依赖的项目根目录运行：

```powershell
python -m pipeline.chapterbar --video news.mp4 --chapters chapters.json --output news-with-chapter-bar.mp4
```

请使用和视频配套的 `chapters.json`。输出必须是新文件，保留原音轨及视频已有的章节信息。工具会输出 JSON 回执。正常日更的回执为 `chapter-bar.json`，记录段名、起点和文件哈希。进度条复用现有 Pillow 和 FFmpeg，不需要下载独立应用或使用 AI 分段。默认使用系统中文字体，也可以用 `--font` 指定。日更配置对应 `navigation.chapter_bar_font`。

如果某期不需要画面底栏，可在 `config/pipeline.json` 的 `navigation` 中设置 `"burn_in_chapter_bar": false`。

底栏样式及标题裁切参考 [ChapterBar](https://github.com/lx-1203/chapterbar/tree/c0f944768d00da945d87a47fc8a40a05e29f5804)，项目内保留 [MIT 许可](licenses/ChapterBar-MIT.txt)。复用框架仅提供源码和配置，制作素材由使用者按授权提供。
