# ROADMAP — ClipForge

## v0.1(当前,已完成)
- [x] 单文件流水线:tts / assets / subs / render / check / all,manifest 幂等续跑
- [x] edge-tts 配音 + sentence 模式中文断句字幕(word 模式备用)
- [x] Pexels(视频/图片)+ Pixabay(视频)+ ComfyUI 兜底链,素材去重与 credits.md
- [x] FFmpeg:视频裁切 1080p / 图片 Ken Burns / concat / 烧字幕 / BGM 混音
- [x] QC:时长差、分辨率、音轨、字幕与来源文件校验
- [x] 横竖版双支持(orientation)

## v0.2(下一步)
- [x] Coverr API 集成(插在 Pexels 视频与 Pixabay 视频之间)
- [x] BGM 池(bgm_pool): 在 project.yaml 中配置多首 BGM 备选,运行时随机选一首
- [ ] 场景转场(xfade 交叉溶解,注意与 concat copy 模式的取舍)
- [ ] BGM 侧链闪避(sidechaincompress,替代固定 12% 音量)
- [ ] 片头/片尾模板(标题卡 drawtext + 订阅提示)
- [x] Pexels 429 自动退避重试

## v0.2.1(IdeaPad 本地化适配, 2026-09-30)
- [x] 字体可移植:SUB_STYLE 硬编码 WenQuanYi Zen Hei / wechat_video 硬编码 wqy-zenhei.ttc → CJK 字体自动探测(Noto Sans CJK SC → WQY → Droid Sans Fallback),字幕 force_style 与 drawtext 共用一个探测函数,找不到即 fail-fast
- [x] 竖屏素材源:cmd_assets 三处 API 请求硬编码 orientation:"landscape" → 跟随 project.orientation,竖屏项目传 portrait(避免横屏素材裁切损失)
- [x] wechat_video 配音音色可配置:CLI --voice / 环境变量 CF_VOICE,默认 zh-CN-YunxiNeural 保持不变
- [x] Pexels 429 退避重试(v0.2 项提前:批量出片稳定性保障,本机生产环境实测需要)

## v0.3(与 TubeForge 打通)
- [x] `topic2yaml`:选题 → DeepSeek 写稿分场景 → 直接产出 project.yaml (tube_forge.py)
- [ ] 批量模式:一次喂 N 个选题,夜间无人值守出片
- [ ] faster-whisper 校对轨(可选):对成片音轨反向识别,diff 文稿查配音事故

## 执行日志
- 2026-07-26 v0.1 初版:SOP + 工具落地,py_compile 通过(容器内无外网,TTS/素材下载待本机实测)
- 2026-07-26 Coverr API 集成:端点 `https://coverr.co/api/videos?query=...&urls=true`,Bearer 认证,插在 Pexels 视频与 Pixabay 视频之间
- 2026-07-26 BGM 池(bgm_pool):project.yaml 支持 bgm_pool 字段,运行随机选一首;向后兼容 bgm 单文件
- 2026-07-26 TubeForge 改造:新建 tube_forge.py,选题→DeepSeek写稿→分场景→project.yaml;tube-forge run 命令可用
- 2026-07-26 清理:删除 test_video 下 generate_tts.py/generate_images.py/synthesize_video.py 旧脚本
- 2026-09-30 v0.2.1 完成:CJK 字体探测命中本机 Noto;竖屏素材参数、wechat_video 音色优先级及 Pexels 429/5xx 退避自测通过;py_compile 通过
