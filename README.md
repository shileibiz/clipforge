# ClipForge — AI 全自动视频剪辑流水线

一条命令,把文字稿变成可上传的 1080p 成片:配音、免版权素材、字幕、BGM、封面、素材来源清单,全自动。

## Quick Start

```bash
pip install edge-tts requests pyyaml
sudo apt install ffmpeg fonts-noto-cjk

cp .env.example .env        # 填入 Pexels/Pixabay key
python clipforge.py init projects/demo
# 编辑 projects/demo/project.yaml 里的 scenes
python clipforge.py all projects/demo
# → projects/demo/output/final.mp4
```

## 命令

| 命令 | 作用 |
|---|---|
| `init` | 生成项目脚手架与 project.yaml 模板 |
| `tts` | edge-tts 逐场景配音,记录精确时长 |
| `assets` | Pexels/Pixabay 搜索下载免版权素材,ComfyUI 兜底,自动去重+来源记录 |
| `subs` | 合并全片 SRT |
| `render` | FFmpeg 渲染:视频裁切 / 图片 Ken Burns → 拼接 → 烧字幕 + BGM |
| `check` | QC:时长/分辨率/音轨校验,产出 qc_report.json |
| `all` | 按序全跑(幂等,可断点续跑) |
| `clean` | 清空 build |

## 产物

```
output/final.mp4        成片(烧录字幕)
output/final.srt        独立字幕(平台软字幕可另传)
output/thumbnail.jpg    封面帧
assets/credits.md       素材来源(免版权溯源)
build/qc_report.json    质检报告
```

## 竖版(Shorts/抖音)

project.yaml 设 `orientation: portrait` 即输出 1080x1920。

详细作业流程见 SOP.md,AI 规约见 CLAUDE.md。
