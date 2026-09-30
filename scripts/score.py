#!/usr/bin/env python3
"""clipforge score: 成片自动 QC + 抽帧, 输出评分模板 projects/<p>/score.md
用法: python score.py projects/t01_kimi_pdf [--round 1]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clipforge import ffprobe_json, media_duration  # noqa: E402

FRAME_TS = (0.10, 0.25, 0.40, 0.55, 0.70, 0.85)  # 全片百分比抽 6 帧


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--round", type=int, default=1)
    args = ap.parse_args()
    proj = Path(args.project)
    final = proj / "output" / "final.mp4"
    if not final.exists():
        final = proj / "output" / "wechat_video.mp4"
    if not final.exists():
        print(f"[score][FATAL] {proj} 没有 output/final.mp4 或 wechat_video.mp4", file=sys.stderr)
        sys.exit(1)

    info = ffprobe_json(final)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = media_duration(final)
    w, h = (v["width"], v["height"]) if v else (0, 0)
    size_mb = int(info["format"].get("size", 0)) / 1048576
    qc = {
        "video": str(final),
        "resolution": f"{w}x{h}",
        "duration_s": round(dur, 1),
        "audio": bool(a),
        "audio_codec": a["codec_name"] if a else "-",
        "size_mb": round(size_mb, 1),
        "bitrate_kbps": int(info["format"].get("bit_rate", 0)) // 1000,
    }

    frames_dir = proj / "build" / f"score_round{args.round}"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for i, pct in enumerate(FRAME_TS, 1):
        ts = max(dur * pct, 0.1)
        subprocess.run([
            "ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", str(final),
            "-frames:v", "1", "-q:v", "2",
            str(frames_dir / f"frame_{i:02d}_{int(pct*100)}pct.jpg"),
        ], capture_output=True, check=False)

    # 字幕轨存在性粗检: 任取一帧人工看; 自动部分记录 srt 条数
    srt = proj / "output" / "final.srt"
    n_sub = 0
    if srt.exists():
        n_sub = srt.read_text(encoding="utf-8").count(" --> ")

    report = f"""# 评分 · {proj.name} · Round {args.round}

## 自动 QC
- 成片: `{qc['video']}`
- 分辨率: {qc['resolution']} (目标 1080x1920 竖屏)
- 时长: {qc['duration_s']}s | 大小: {qc['size_mb']}MB | 码率: {qc['bitrate_kbps']}kbps
- 音轨: {qc['audio_codec'] if qc['audio'] else '缺失❌'} | 字幕条数: {n_sub}

## 抽帧 (build/score_round{args.round}/, 6 帧覆盖 10%~85%)
逐帧检查项: 画面清晰度 / 素材与口播相关性 / 字幕完整不出屏 / 无水印 / 构图可用

## CC 评分 (1-5)
- 钩子(前3秒抓人): _
- 素材匹配度: _
- 字幕质量: _
- 配音自然度: _
- 整体完成度: _

## 优化项 (下一轮)
- _
"""
    out = proj / f"score_round{args.round}.md"
    out.write_text(report, encoding="utf-8")
    (proj / "build" / "qc_auto.json").write_text(
        json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[score] {out}")
    print(f"[score] frames -> {frames_dir}")
    print("[score] auto-QC:", json.dumps(qc, ensure_ascii=False))


if __name__ == "__main__":
    main()
