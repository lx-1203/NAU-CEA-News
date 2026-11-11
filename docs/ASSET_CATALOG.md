# 复用资产目录

共享素材直接存放在仓库的 `assets/` 下。按分类浏览，可单独选取文件。[素材索引](../assets/README.md)

- 画面、片尾和配音参考以 `assets/qualified-assets.json` 记录的相对路径、文件大小及 SHA256 为准。克隆仓库后可运行 `python scripts/verify_assets.py` 验证。
- 曲目、录音校验值和来源记录在 `assets/audio/music/MANIFEST.json`。正式渲染选曲后再核对所用录音。[自动 BGM](BGM.md)
- 首次安装从固定来源下载语音模型和依赖。使用者按新一期选取有权使用的新闻配图、原视频和资料，并记录来源。[快速开始](../QUICK_START.md) · [素材规范](VISUAL_MATERIAL_POLICY.md)

校验值用于确认文件与清单一致。素材的署名和使用范围以各目录说明为准。
