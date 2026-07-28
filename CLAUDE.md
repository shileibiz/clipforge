# CLAUDE.md — ClipForge (AI-facing 规约)

## Purpose
把"文字稿 → 成片"的人工剪辑流程完全自动化。CC 是唯一执行者,产出可直接上传
YouTube/B站 的 1080p 成片(含烧录字幕、BGM、封面帧、素材来源清单)。

## SOP 引用
**脚本写作规范、场景拆分规则、关键词规则、TTS 友好性、自检清单 → 详见 `SOP.md` §2-§3**
**禁止重犯清单、故障处置表 → 详见 `SOP.md` §4-§5**
本文件只记录与代码交互直接相关的工程规则。

## Architecture
- 单文件 CLI:`clipforge.py`,零框架,依赖仅 edge-tts / requests / pyyaml + 系统 ffmpeg
- 状态机:`build/manifest.json` 记录每场景 `audio_ok / duration / asset / asset_ok`
  ,所有阶段以 manifest 判断跳过与续跑(幂等)
- 流水线阶段:`tts → assets → subs → render → check`,`all` 串行执行
- 素材兜底链:Pexels 视频 → Coverr 视频 → Pixabay 视频 → Pexels 图片 → Unsplash 图片 → ComfyUI 本地生图 → fail-fast
- 时间轴真源:每场景 mp3 的 ffprobe 时长;字幕与视频时长全部由它推导

## Engineering Rules (CC 必须遵守)
1. 失败即停(fail-fast),按 SOP.md §4 故障表处置后重跑同一命令,禁止绕过 QC
2. 修改素材源优先级/新增素材站:只允许在 `cmd_assets` 的兜底链里加函数,不改调用方
3. `render` 的编码参数(1080p/30fps/CRF20/yuv420p)是平台兼容性底线,禁止随意改
4. subtitle_mode 默认 sentence(中文断句均摊);word 模式仅英文内容启用
5. 新增功能先写进 ROADMAP.md 再动手,完成后勾选并记一行结果

## Interfaces
- 输入:`<proj>/project.yaml`(完整字段定义见 SOP.md §6)
- 输出:`<proj>/output/{final.mp4, final.srt, thumbnail.jpg}` + `<proj>/assets/credits.md`
- 上游:TubeForge 脚本生成器直接产出 project.yaml(见 tube_forge.py)
- 环境:.env 提供 PEXELS_API_KEY / PIXABAY_API_KEY / COVERR_API_KEY / UNSPLASH_ACCESS_KEY / COMFYUI_API  (关键词由 CC 自动提取,无需 API key)
