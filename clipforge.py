#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ClipForge — AI 全自动视频剪辑流水线(供 Claude Code 调用)

流程: 文字稿 → TTS(edge-tts) → 无版权素材搜索(Pexels/Pixabay/ComfyUI兜底)
      → 字幕SRT → FFmpeg 逐场景渲染+拼接+烧字幕+BGM → QC 检查 → 成片

用法:
  python clipforge.py init  <项目目录>          # 生成项目脚手架 project.yaml
  python clipforge.py tts   <项目目录>          # 逐场景合成语音 + 记录时长
  python clipforge.py assets <项目目录>         # 逐场景搜索并下载无版权素材
  python clipforge.py subs  <项目目录>          # 生成全片 SRT
  python clipforge.py render <项目目录>         # FFmpeg 渲染成片
  python clipforge.py check <项目目录>          # QC 检查(时长/分辨率/音轨)
  python clipforge.py all   <项目目录>          # 按顺序跑完整条流水线
  python clipforge.py clean <项目目录>          # 清理 build 产物(保留素材)

环境变量(.env 或 shell 导出):
  PEXELS_API_KEY    必填其一   https://www.pexels.com/api/
  PIXABAY_API_KEY   必填其一   https://pixabay.com/api/docs/
  COVERR_API_KEY    可选       https://coverr.co/developers  (Bearer token)
  UNSPLASH_ACCESS_KEY 可选     https://unsplash.com/developers
  CC (claude CLI)  自动提取    场景未写 keywords 时提取英文搜索词(替换原 DeepSeek API)
  COMFYUI_API       可选       本地生图兜底,如 http://192.168.1.10:8188

依赖: pip install edge-tts requests pyyaml   (系统需装 ffmpeg/ffprobe)
"""

import argparse
import asyncio
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    print("缺少依赖: pip install pyyaml requests edge-tts", file=sys.stderr)
    sys.exit(1)

import requests

# ---------------- 全局常量 ----------------
W, H, FPS = 1920, 1080, 30
CRF = 20
PRESET = "medium"
# ---------------- 基础工具 ----------------

def log(msg):
    print(f"[clipforge] {msg}", flush=True)


def die(msg):
    print(f"[clipforge][FATAL] {msg}", file=sys.stderr)
    sys.exit(1)


def find_cjk_font():
    """按优先级返回 (字体家族名, 字体文件路径)。"""
    fonts = (
        ("Noto Sans CJK SC", "NotoSansCJKsc-*.otf"),
        ("WenQuanYi Zen Hei", "wqy-zenhei.ttc"),
        ("Droid Sans Fallback", "DroidSansFallback.ttf"),
    )
    roots = (Path.home() / ".local/share/fonts", Path("/usr/local/share/fonts"),
             Path("/usr/share/fonts"))
    for family, filename in fonts:
        if shutil.which("fc-match"):
            result = subprocess.run(
                ["fc-match", f"{family}:lang=zh", "-f", "%{family}\n%{file}\n"],
                capture_output=True, text=True, check=False,
            )
            lines = result.stdout.splitlines()
            if (result.returncode == 0 and len(lines) >= 2
                    and family in (name.strip() for name in lines[0].split(","))
                    and Path(lines[1]).is_file()):
                return family, lines[1]
        for root in roots:
            if root.is_dir():
                for path in root.rglob(filename):
                    if path.is_file():
                        return family, str(path)
    die("未找到中文字体(Noto Sans CJK SC / WenQuanYi Zen Hei / Droid Sans Fallback)")


def sub_style(font_name=None):
    if font_name is None:
        font_name, _ = find_cjk_font()
    return (
        f"FontName={font_name},FontSize=16,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
        "MarginV=40,Alignment=2"
    )


def run(cmd, quiet=True):
    """执行外部命令,失败即终止(fail-fast,便于 CC 定位问题)。"""
    r = subprocess.run(cmd, capture_output=quiet, text=True)
    if r.returncode != 0:
        err = (r.stderr or "")[-2000:] if quiet else ""
        die(f"命令失败: {' '.join(map(str, cmd))}\n{err}")
    return r


def load_env(proj: Path):
    """加载项目目录或当前目录下的 .env(不覆盖已有环境变量)。"""
    for p in (proj / ".env", Path(".env")):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_project(proj: Path) -> dict:
    f = proj / "project.yaml"
    if not f.exists():
        die(f"找不到 {f},先执行 init")
    cfg = yaml.safe_load(f.read_text(encoding="utf-8"))
    if not cfg.get("scenes"):
        die("project.yaml 中 scenes 为空")
    for i, sc in enumerate(cfg["scenes"]):
        if not sc.get("text", "").strip():
            die(f"场景 {i+1} 缺少 text")
    return cfg


def manifest_path(proj: Path) -> Path:
    return proj / "build" / "manifest.json"


def load_manifest(proj: Path) -> dict:
    p = manifest_path(proj)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"scenes": {}}


def save_manifest(proj: Path, m: dict):
    p = manifest_path(proj)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def ffprobe_json(path: Path) -> dict:
    r = run(["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(path)])
    return json.loads(r.stdout)


def media_duration(path: Path) -> float:
    return float(ffprobe_json(path)["format"]["duration"])


def stream_duration(path: Path, kind: str, info: dict = None) -> float:
    """单条视频/音频流时长(容器时长取各流最大值, 会掩盖某一轨提前结束)。无该流返回 0。"""
    info = info or ffprobe_json(path)
    for s in info["streams"]:
        if s.get("codec_type") == kind:
            if s.get("duration"):
                return float(s["duration"])
            return float(info["format"]["duration"])
    return 0.0


def fmt_srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ---------------- init ----------------

TEMPLATE_YAML = """\
# ClipForge 项目配置 —— 一个场景 = 一段口播 + 一个画面素材
title: 示例:三分钟看懂复利
voice: zh-CN-YunxiNeural        # edge-tts 声音, 英文可用 en-US-AndrewNeural
rate: "+8%"                     # 语速微调
subtitle_mode: sentence         # sentence=按句均摊时间(中文推荐) / word=edge-tts词级时间轴
bgm: ""                         # 可选: BGM 文件路径(相对项目目录), 自动降到 12% 音量循环
bgm_volume: 0.12
# bgm_pool:                     # 可选: BGM 池(替代 bgm), 从 pool 中随机选一首
#   - path: music/upbeat.mp3
#     tags: [轻松, 励志, 科技感]
#   - path: music/cinematic.mp3
#     tags: [科技感, 震撼]
orientation: landscape          # landscape=1920x1080 / portrait=1080x1920(竖版)

scenes:
  - text: 你有没有想过,为什么巴菲特99%的财富是在50岁之后才赚到的?答案只有两个字:复利。
    keywords: [money growth, compound interest]   # 英文搜索词,留空则用 DeepSeek 自动提取
    asset_type: video                             # video / image / auto
  - text: 假设你每个月定投一千元,年化收益百分之八,三十年后你会拥有接近一百五十万。
    keywords: [stock chart, investment]
    asset_type: video
  - text: 时间才是复利最重要的变量。越早开始,雪球滚得越大。
    keywords: [snowball, winter mountain]
    asset_type: video
"""


def cmd_init(proj: Path):
    proj.mkdir(parents=True, exist_ok=True)
    for d in ("audio", "assets", "build", "output"):
        (proj / d).mkdir(exist_ok=True)
    f = proj / "project.yaml"
    if f.exists():
        log(f"{f} 已存在,跳过")
    else:
        f.write_text(TEMPLATE_YAML, encoding="utf-8")
        log(f"已生成 {f},编辑 scenes 后执行: python clipforge.py all {proj}")


# ---------------- tts ----------------

def split_sentences(text: str):
    """中英混合分句,用于 sentence 字幕模式。"""
    parts = re.split(r"(?<=[。!?!?;;])\s*", text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    # 过长句子按逗号二次切分,保证单条字幕不超过 ~28 字
    out = []
    for p in parts:
        if len(p) <= 28:
            out.append(p)
        else:
            frags = [q.strip() for q in re.split(r"(?<=[,,、])\s*", p) if q.strip()]
            # 短片段(顿号/逗号切出的碎片)并入邻段, 避免出现"小红书封面、"式残条
            merged = []
            for q in frags:
                if merged and (len(merged[-1]) <= 6 or
                               (len(q) <= 6 and len(merged[-1]) + len(q) <= 30)):
                    merged[-1] += q
                else:
                    merged.append(q)
            out.extend(merged)
    return out or [text.strip()]


async def _tts_one(text, voice, rate, mp3: Path, srt: Path, mode: str):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate)
    sub = edge_tts.SubMaker()
    with open(mp3, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                try:
                    sub.feed(chunk)
                except Exception:
                    pass
    if mode == "word":
        try:
            srt.write_text(sub.get_srt(), encoding="utf-8")
            return
        except Exception:
            pass  # 回落到 sentence 模式
    # sentence 模式: 按句子字符数均摊本场景音频时长
    dur = media_duration(mp3)
    sents = split_sentences(text)
    total_chars = sum(len(s) for s in sents) or 1
    t, lines = 0.0, []
    for i, s in enumerate(sents, 1):
        d = dur * len(s) / total_chars
        lines.append(f"{i}\n{fmt_srt_time(t)} --> {fmt_srt_time(min(t + d, dur))}\n{s}\n")
        t += d
    srt.write_text("\n".join(lines), encoding="utf-8")


def cmd_tts(proj: Path):
    cfg = load_project(proj)
    m = load_manifest(proj)
    voice = cfg.get("voice", "zh-CN-YunxiNeural")
    rate = cfg.get("rate", "+0%")
    mode = cfg.get("subtitle_mode", "sentence")
    for i, sc in enumerate(cfg["scenes"], 1):
        key = f"{i:02d}"
        mp3 = proj / "audio" / f"scene_{key}.mp3"
        srt = proj / "audio" / f"scene_{key}.srt"
        if mp3.exists() and m["scenes"].get(key, {}).get("audio_ok"):
            log(f"场景{key} 音频已存在,跳过")
            continue
        log(f"场景{key} TTS: {sc['text'][:24]}…")
        asyncio.run(_tts_one(sc["text"], sc.get("voice", voice),
                             sc.get("rate", rate), mp3, srt, mode))
        dur = media_duration(mp3)
        if dur < 0.5:
            die(f"场景{key} 音频异常(时长 {dur:.2f}s),检查网络或文本")
        m["scenes"].setdefault(key, {})
        m["scenes"][key].update({"audio_ok": True, "duration": round(dur, 3)})
        save_manifest(proj, m)
        log(f"场景{key} 完成, 时长 {dur:.1f}s")
    total = sum(s["duration"] for s in m["scenes"].values())
    log(f"TTS 全部完成, 总口播时长 {total:.1f}s")


# ---------------- assets ----------------

def extract_keywords_cc(narration_text: str) -> list:
    """通过 CC (Claude Code) 从口播文字提取 2 个具体素材关键词。"""
    prompt = (
        f"From this narration, suggest exactly 2 concrete, visual b-roll keywords "
        f"(camera can film them). Return as JSON array [\"keyword1\", \"keyword2\"]. "
        f"No abstract words. Narration: {narration_text}"
    )
    try:
        result = subprocess.run(
            ["claude", "--model", "claude-opus-5", "--effort", "high", "--print", "-p", prompt],
            capture_output=True, text=True, timeout=30
        )
        raw = result.stdout.strip()
        # Strip markdown code fence if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            raw = raw.strip()
        arr = json.loads(raw)
        return [str(a) for a in arr][:2]
    except Exception as e:
        log(f"CC 关键词提取失败({e}),回落为通用词")
        return []


def pexels_get(url, key, params):
    """429/5xx 最多重试三次，等待 2/4/8 秒。"""
    for attempt in range(4):
        response = requests.get(url, headers={"Authorization": key},
                                params=params, timeout=30)
        if response.status_code != 429 and not 500 <= response.status_code <= 599:
            return response
        if attempt == 3:
            response.raise_for_status()
            return response
        delay = 2 ** (attempt + 1)
        log(f"Pexels HTTP {response.status_code}，{delay}s 后重试")
        time.sleep(delay)


def _pick_long_enough(cands, min_dur):
    """cands: [(素材时长或None, 结果)] 按 API 相关度排序。优先取首个时长 ≥ 场景时长的;
    都不够长则取最长的(render 阶段 stream_loop + tpad 补足视频轨)。"""
    if not cands:
        return None
    for d, found in cands:
        if d is not None and d >= min_dur:
            return found
    return max(cands, key=lambda c: c[0] or 0)[1]


def pexels_video(kw, used: set, orientation="landscape", min_dur=0.0):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return None
    try:
        r = pexels_get("https://api.pexels.com/videos/search", key,
                       {"query": kw, "per_page": 8, "orientation": orientation})
        cands = []
        for v in r.json().get("videos", []):
            if f"pexels-v-{v['id']}" in used:
                continue
            files = sorted([f for f in v["video_files"]
                            if f.get("width") and f["width"] >= 1280],
                           key=lambda f: -f["width"])
            if files:
                cands.append((v.get("duration"),
                              {"kind": "video", "url": files[0]["link"],
                               "id": f"pexels-v-{v['id']}", "ext": ".mp4",
                               "credit": f"Pexels video {v['url']}"}))
        return _pick_long_enough(cands, min_dur)
    except Exception as e:
        log(f"Pexels 视频搜索失败: {e}")
    return None


def pexels_photo(kw, used: set, orientation="landscape"):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return None
    try:
        r = pexels_get("https://api.pexels.com/v1/search", key,
                       {"query": kw, "per_page": 8, "orientation": orientation})
        for p in r.json().get("photos", []):
            if f"pexels-p-{p['id']}" in used:
                continue
            return {"kind": "image", "url": p["src"]["large2x"],
                    "id": f"pexels-p-{p['id']}", "ext": ".jpg",
                    "credit": f"Pexels photo {p['url']}"}
    except Exception as e:
        log(f"Pexels 图片搜索失败: {e}")
    return None


def unsplash_photo(kw, used: set, orientation="landscape"):
    """Unsplash 免版权图片搜索 (在 pexels_photo 之后兜底)。
    端点: GET https://api.unsplash.com/search/photos
    认证: Authorization: Client-ID {ACCESS_KEY}
    返回格式同 pexels_photo()。
    """
    key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not key:
        return None
    try:
        r = requests.get("https://api.unsplash.com/search/photos",
                         headers={"Authorization": f"Client-ID {key}"},
                         params={"query": kw, "per_page": 8,
                                 "orientation": orientation}, timeout=30)
        for p in r.json().get("results", []):
            if f"unsplash-p-{p['id']}" in used:
                continue
            url = (p.get("urls") or {}).get("raw") or (p.get("urls") or {}).get("full")
            if not url:
                continue
            return {"kind": "image", "url": url,
                    "id": f"unsplash-p-{p['id']}", "ext": ".jpg",
                    "credit": f"Unsplash photo by {p.get('user',{}).get('name','unknown')} ({p['id']})"}
    except Exception as e:
        log(f"Unsplash 图片搜索失败: {e}")
    return None


def pixabay_video(kw, used: set, orientation="landscape", min_dur=0.0):
    """Pixabay 视频 API 无 orientation 参数, 按返回文件宽高本地过滤方向。"""
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return None
    try:
        r = requests.get("https://pixabay.com/api/videos/",
                         params={"key": key, "q": kw, "per_page": 8}, timeout=30)
        cands = []
        for v in r.json().get("hits", []):
            if f"pixabay-v-{v['id']}" in used:
                continue
            vf = v["videos"].get("large") or v["videos"].get("medium")
            if not (vf and vf.get("url")):
                continue
            fw, fh = vf.get("width") or 0, vf.get("height") or 0
            if fw and fh and (fh > fw) != (orientation == "portrait"):
                continue
            cands.append((v.get("duration"),
                          {"kind": "video", "url": vf["url"],
                           "id": f"pixabay-v-{v['id']}", "ext": ".mp4",
                           "credit": f"Pixabay video {v.get('pageURL','')}"}))
        return _pick_long_enough(cands, min_dur)
    except Exception as e:
        log(f"Pixabay 视频搜索失败: {e}")
    return None


def coverr_video(kw, used: set, min_dur=0.0):
    """Coverr 免版权视频搜索 (插在 Pexels 与 Pixabay 之间)。
    端点: https://coverr.co/api/videos?query=...&urls=true
    认证: Authorization: Bearer {COVERR_API_KEY}
    返回格式同 pexels_video()。
    """
    key = os.environ.get("COVERR_API_KEY")
    if not key:
        return None
    try:
        r = requests.get("https://coverr.co/api/videos",
                         headers={"Authorization": f"Bearer {key}"},
                         params={"query": kw, "urls": "true",
                                 "page_size": 8, "page": 0},
                         timeout=30)
        cands = []
        for v in r.json().get("hits", []):
            if f"coverr-v-{v['id']}" in used:
                continue
            urls = v.get("urls")
            if urls and urls.get("mp4"):
                cands.append((v.get("duration"),
                              {"kind": "video", "url": urls["mp4"],
                               "id": f"coverr-v-{v['id']}", "ext": ".mp4",
                               "credit": f"Coverr video {v.get('slug', v['id'])}"}))
        return _pick_long_enough(cands, min_dur)
    except Exception as e:
        log(f"Coverr 视频搜索失败: {e}")
    return None


def comfyui_image(prompt: str, out: Path):
    """本地 ComfyUI 兜底生图。依赖你已有的 HTTP API 封装:
    POST {COMFYUI_API}/generate  {"prompt": "..."} → 返回图片二进制。
    如你的封装不同,只需改这一个函数。"""
    api = os.environ.get("COMFYUI_API")
    if not api:
        return False
    try:
        r = requests.post(f"{api.rstrip('/')}/generate",
                          json={"prompt": prompt}, timeout=300)
        if r.status_code == 200 and r.content:
            out.write_bytes(r.content)
            return True
    except Exception as e:
        log(f"ComfyUI 生图失败: {e}")
    return False


def download(url: str, out: Path):
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(out, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)


def cmd_assets(proj: Path):
    cfg = load_project(proj)
    orientation = "portrait" if cfg.get("orientation") == "portrait" else "landscape"
    m = load_manifest(proj)
    used = {s.get("asset_id") for s in m["scenes"].values() if s.get("asset_id")}
    credits = []
    for i, sc in enumerate(cfg["scenes"], 1):
        key = f"{i:02d}"
        rec = m["scenes"].setdefault(key, {})
        if rec.get("asset_ok") and rec.get("asset") and (proj / rec["asset"]).exists():
            log(f"场景{key} 素材已存在,跳过")
            continue
        kws = sc.get("keywords") or extract_keywords_cc(sc["text"]) or ["abstract background"]
        want = sc.get("asset_type", "auto")
        need = rec.get("duration") or 0.0   # 场景口播时长, 视频素材优先选不短于它的
        found = None
        for kw in kws:
            if want in ("video", "auto"):
                found = (pexels_video(kw, used, orientation, min_dur=need)
                         or coverr_video(kw, used, min_dur=need)
                         or pixabay_video(kw, used, orientation, min_dur=need))
            if not found and want in ("image", "auto"):
                found = pexels_photo(kw, used, orientation) or unsplash_photo(kw, used, orientation)
            if found:
                log(f"场景{key} 命中素材 [{kw}] → {found['id']}")
                break
        out = proj / "assets" / f"scene_{key}"
        if found:
            out = out.with_suffix(found["ext"])
            download(found["url"], out)
            rec.update({"asset": str(out.relative_to(proj)), "asset_kind": found["kind"],
                        "asset_id": found["id"], "asset_ok": True})
            used.add(found["id"])
            credits.append(f"scene_{key}: {found['credit']}")
        else:
            # 兜底: ComfyUI 生图
            out = out.with_suffix(".png")
            prompt = ", ".join(kws) + ", cinematic, high quality, 16:9"
            if comfyui_image(prompt, out):
                rec.update({"asset": str(out.relative_to(proj)), "asset_kind": "image",
                            "asset_id": f"comfyui-{key}", "asset_ok": True})
                credits.append(f"scene_{key}: ComfyUI 本地生成 ({prompt})")
                log(f"场景{key} ComfyUI 兜底生图完成")
            else:
                die(f"场景{key} 所有素材源均失败,关键词: {kws} —— "
                    f"请检查 API key,或换 keywords 后重跑 assets")
        save_manifest(proj, m)
    if credits:
        (proj / "assets" / "credits.md").write_text(
            "# 素材来源(免版权)\n\n" + "\n".join(f"- {c}" for c in credits) + "\n",
            encoding="utf-8")
    log("素材阶段完成, 来源已写入 assets/credits.md")


# ---------------- subs ----------------

def parse_srt(path: Path):
    items = []
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip())
    for b in blocks:
        lines = b.strip().splitlines()
        if len(lines) >= 3:
            mm = re.match(r"([\d:,]+)\s*-->\s*([\d:,]+)", lines[1])
            if mm:
                def to_s(t):
                    h, mn, rest = t.split(":")
                    s, ms = rest.split(",")
                    return int(h) * 3600 + int(mn) * 60 + int(s) + int(ms) / 1000
                items.append((to_s(mm.group(1)), to_s(mm.group(2)),
                              " ".join(lines[2:])))
    return items


XFADE_DEFAULT = 0.3   # 普通场景间转场
XFADE_SECTION = 0.5   # section 切换(hook→setup 等)用更长转场


def _trans_durs(durations: list, sections: list) -> list:
    """每对相邻 scene 的转场时长(与 render 的 xfade/acrossfade 参数保持同一套数学)。"""
    tds = []
    for i in range(len(durations) - 1):
        td = XFADE_SECTION if sections[i] != sections[i + 1] else XFADE_DEFAULT
        # 极短场景保护: 转场时长不超过 scene 的 40%
        if durations[i] < 1.0:
            td = min(td, durations[i] * 0.3)
        tds.append(td)
    return tds


def _scene_starts(cfg: dict, m: dict):
    """每个 scene 在成片中的真实起点(xfade 重叠已扣除)与全片期望时长。"""
    N = len(cfg["scenes"])
    durations = []
    for i in range(1, N + 1):
        rec = m["scenes"].get(f"{i:02d}")
        durations.append(rec["duration"] if rec and rec.get("duration") else 0.0)
    sections = [sc.get("section", "") for sc in cfg["scenes"]]
    tds = _trans_durs(durations, sections)
    starts, t = [], 0.0
    for i in range(N):
        starts.append(t)
        if i < N - 1:
            t += durations[i] - tds[i]
    expected = (starts[-1] + durations[-1]) if N else 0.0
    return starts, expected


def cmd_subs(proj: Path):
    cfg = load_project(proj)
    m = load_manifest(proj)
    starts, expected = _scene_starts(cfg, m)
    idx, out_lines = 0, []
    for i in range(1, len(cfg["scenes"]) + 1):
        key = f"{i:02d}"
        rec = m["scenes"].get(key) or die(f"场景{key} 未跑 tts")
        srt = proj / "audio" / f"scene_{key}.srt"
        if not srt.exists():
            die(f"缺少 {srt},先跑 tts")
        offset = starts[i - 1]
        for st, en, txt in parse_srt(srt):
            idx += 1
            out_lines.append(f"{idx}\n{fmt_srt_time(st + offset)} --> "
                             f"{fmt_srt_time(en + offset)}\n{txt}\n")
    final = proj / "build" / "final.srt"
    final.parent.mkdir(exist_ok=True)
    final.write_text("\n".join(out_lines), encoding="utf-8")
    log(f"全片字幕已生成: {final} (共 {idx} 条, 总长 {expected:.1f}s)")


# ---------------- render ----------------

def scene_size(cfg):
    return (1080, 1920) if cfg.get("orientation") == "portrait" else (W, H)


def render_scene(proj: Path, cfg, key: str, rec: dict) -> Path:
    w, h = scene_size(cfg)
    asset = proj / rec["asset"]
    audio = proj / "audio" / f"scene_{key}.mp3"
    out = proj / "build" / f"clip_{key}.mp4"
    dur = rec["duration"]
    # 跳过判断看视频流时长: 容器时长取最长轨, 会放过视频轨不足的旧片段
    if out.exists() and abs(stream_duration(out, "video") - dur) < 0.5:
        log(f"场景{key} 片段已渲染,跳过")
        return out
    if rec["asset_kind"] == "video":
        # 素材短于口播: stream_loop 循环素材; 万一循环失效, tpad 冻结末帧兜底;
        # 由 -t 截到场景时长(不用 -shortest, 避免掩盖视频轨不足)
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
              f"crop={w}:{h},fps={FPS},setsar=1,"
              f"tpad=stop_mode=clone:stop_duration={dur:.3f}")
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(asset),
             "-i", str(audio), "-t", f"{dur:.3f}",
             "-filter_complex", f"[0:v]{vf}[v]",
             "-map", "[v]", "-map", "1:a",
             "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
             str(out)])
    else:  # 图片 → Ken Burns 缓推
        frames = max(int(dur * FPS), 1)
        vf = (f"scale={w*2}:-2,"
              f"zoompan=z='min(zoom+0.0006,1.15)':d={frames}"
              f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":s={w}x{h}:fps={FPS},setsar=1")
        run(["ffmpeg", "-y", "-loop", "1", "-i", str(asset),
             "-i", str(audio), "-t", f"{dur:.3f}",
             "-filter_complex", f"[0:v]{vf}[v]",
             "-map", "[v]", "-map", "1:a",
             "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
             "-shortest", str(out)])
    vdur = stream_duration(out, "video")
    if vdur < dur - 0.5:
        die(f"场景{key} 片段视频轨 {vdur:.2f}s < 口播 {dur:.2f}s,检查素材 {asset} 是否损坏")
    log(f"场景{key} 渲染完成 ({dur:.1f}s)")
    return out


def cmd_render(proj: Path):
    cfg = load_project(proj)
    subtitle_style = sub_style()
    m = load_manifest(proj)
    build = proj / "build"
    clips = []
    for i in range(1, len(cfg["scenes"]) + 1):
        key = f"{i:02d}"
        rec = m["scenes"].get(key)
        if not (rec and rec.get("audio_ok") and rec.get("asset_ok")):
            die(f"场景{key} 前置阶段未完成(tts/assets)")
        clips.append(render_scene(proj, cfg, key, rec))

    N = len(clips)
    merged = build / "merged.mp4"
    durations = [rec["duration"] for rec in
                 (m["scenes"].get(f"{i:02d}") for i in range(1, N + 1))]
    sections = [sc.get("section", "") for sc in cfg["scenes"]]
    trans_durs = _trans_durs(durations, sections)

    if N == 1:
        # 单场景直接拷贝
        shutil.copy2(clips[0], merged)
    else:
        # --- xfade 转场: 相邻 scene 交叉淡入淡出 ---
        # 构建 filtergraph
        vf_parts = []
        af_parts = []
        for i in range(N):
            vf_parts.append(f"[{i}:v]settb=AVTB[v{i}];")
            af_parts.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}];")

        # xfade offset = 后一 clip 在成片时间轴上的真实起点(重叠已扣除)
        starts, _expected = _scene_starts(cfg, m)
        for i in range(1, N):
            td = trans_durs[i - 1]
            xfoff = max(0.0, starts[i])
            if i == 1:
                vf_parts.append(
                    f"[v0][v1]xfade=transition=fade:duration={td:.3f}:offset={xfoff:.3f}[c1];")
                af_parts.append(
                    f"[a0][a1]acrossfade=d={td:.3f}[ac1];")
            else:
                vf_parts.append(
                    f"[c{i-1}][v{i}]xfade=transition=fade:duration={td:.3f}:offset={xfoff:.3f}[c{i}];")
                af_parts.append(
                    f"[ac{i-1}][a{i}]acrossfade=d={td:.3f}[ac{i}];")

        final_v_label = f"c{N-1}"
        final_a_label = f"ac{N-1}"

        filter_str = "".join(vf_parts + af_parts).rstrip(";")

        input_args = []
        for c in clips:
            input_args.extend(["-i", str(c)])

        run(["ffmpeg", "-y"] + input_args +
            ["-filter_complex", filter_str,
             "-map", f"[{final_v_label}]",
             "-map", f"[{final_a_label}]",
             "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
             "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k",
             str(merged)])
        log(f"xfade 转场完成 ({N} 场景, {N-1} 处过渡)")

    # 落盘真实场景时间轴(字幕/QC/后续优化的唯一真源)
    starts, expected = _scene_starts(cfg, m)
    timeline = {"scene_starts": starts, "scene_durations": durations if N > 1 else
                [m["scenes"].get("01", {}).get("duration", 0.0)],
                "trans_durs": trans_durs if N > 1 else [],
                "expected_duration": round(expected, 3),
                "final_duration": round(media_duration(merged), 3)}
    (build / "timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- 字幕(烧录) + BGM + sidechain 闪避 ---
    srt = build / "final.srt"
    if not srt.exists():
        cmd_subs(proj)
    final = proj / "output" / "final.mp4"
    final.parent.mkdir(exist_ok=True)
    srt_esc = str(srt.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    sub_filter = f"subtitles='{srt_esc}':force_style='{subtitle_style}'"

    # BGM 选择: bgm_pool > bgm > 无 BGM
    bgm_path = None
    vol = cfg.get("bgm_volume", 0.12)

    pool = cfg.get("bgm_pool")
    if pool and isinstance(pool, list):
        available = [p for p in pool if (proj / p["path"]).exists()]
        if available:
            chosen = random.choice(available)
            bgm_path = proj / chosen["path"]
            tags = chosen.get("tags", [])
            tag_str = f" ({', '.join(tags)})" if tags else ""
            log(f"BGM 池: 选中 {chosen['path']}{tag_str}")
        else:
            log("BGM 池中的文件均不存在,跳过 BGM")
    else:
        bgm = cfg.get("bgm", "")
        if bgm and (proj / bgm).exists():
            bgm_path = proj / bgm

    if bgm_path:
        # sidechain 闪避: 配音时 BGM 自动降低音量
        run(["ffmpeg", "-y", "-i", str(merged),
             "-stream_loop", "-1", "-i", str(bgm_path),
             "-filter_complex",
             f"[0:v]{sub_filter}[v];"
             f"[1:a]volume={vol}[bgm];"
             f"[0:a]asplit[voice][voice_sc];"
             f"[bgm][voice_sc]sidechaincompress=threshold=0.06:ratio=10:attack=1:release=100[bgm_ducked];"
             f"[voice][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2[a]",
             "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-shortest", str(final)])
        log("sidechain 闪避已应用 (配音时 BGM 自动降低)")
    else:
        run(["ffmpeg", "-y", "-i", str(merged),
             "-vf", sub_filter,
             "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
             "-pix_fmt", "yuv420p", "-c:a", "copy", str(final)])
    # 顺带出封面帧 + 独立 srt(平台软字幕可另传)
    run(["ffmpeg", "-y", "-i", str(final), "-ss", "1", "-frames:v", "1",
         str(proj / "output" / "thumbnail.jpg")])
    shutil.copy(srt, proj / "output" / "final.srt")
    log(f"成片输出: {final}")


# ---------------- check ----------------

def cmd_check(proj: Path):
    cfg = load_project(proj)
    m = load_manifest(proj)
    final = proj / "output" / "final.mp4"
    if not final.exists():
        die("找不到成片,先跑 render")
    info = ffprobe_json(final)
    vdur = float(info["format"]["duration"])
    vtrack = stream_duration(final, "video", info)
    atrack = stream_duration(final, "audio", info)
    adur_total = sum(s["duration"] for s in m["scenes"].values())
    # xfade 重叠会吞掉部分时长, 期望值以 timeline.json(真实时间轴)为准
    tl_path = proj / "build" / "timeline.json"
    expected_final = None
    if tl_path.exists():
        try:
            expected_final = json.loads(tl_path.read_text(encoding="utf-8")).get("expected_duration")
        except Exception:
            expected_final = None
    ref_dur = expected_final if expected_final else adur_total
    vstreams = [s for s in info["streams"] if s["codec_type"] == "video"]
    astreams = [s for s in info["streams"] if s["codec_type"] == "audio"]
    w, h = scene_size(cfg)
    report = {
        "file": str(final),
        "duration": round(vdur, 2),
        "expected_duration": round(ref_dur, 2),
        "raw_narration_duration": round(adur_total, 2),
        "duration_delta": round(abs(vdur - ref_dur), 2),
        "video_track_duration": round(vtrack, 2),
        "audio_track_duration": round(atrack, 2),
        "video_track_delta": round(abs(vtrack - ref_dur), 2),
        "audio_track_delta": round(abs(atrack - ref_dur), 2),
        "resolution": f"{vstreams[0]['width']}x{vstreams[0]['height']}" if vstreams else "none",
        "has_audio": bool(astreams),
        "srt_exists": (proj / "output" / "final.srt").exists(),
        "credits_exists": (proj / "assets" / "credits.md").exists(),
    }
    problems = []
    if report["duration_delta"] > 1.5:
        problems.append(f"成片与口播总时长差 {report['duration_delta']}s > 1.5s")
    # 容器时长取最长轨, 视频轨提前结束(后段黑屏)只能分轨校验才拦得住
    if vstreams and report["video_track_delta"] > 1.5:
        problems.append(f"视频轨时长 {report['video_track_duration']}s 与期望时间轴 "
                        f"{report['expected_duration']}s 差 {report['video_track_delta']}s > 1.5s")
    if astreams and report["audio_track_delta"] > 1.5:
        problems.append(f"音频轨时长 {report['audio_track_duration']}s 与期望时间轴 "
                        f"{report['expected_duration']}s 差 {report['audio_track_delta']}s > 1.5s")
    if vstreams and (vstreams[0]["width"], vstreams[0]["height"]) != (w, h):
        problems.append(f"分辨率 {report['resolution']} != {w}x{h}")
    if not astreams:
        problems.append("成片无音轨")
    report["problems"] = problems
    report["pass"] = not problems
    (proj / "build" / "qc_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(json.dumps(report, ensure_ascii=False, indent=2))
    if problems:
        die("QC 未通过: " + "; ".join(problems))
    log("QC 通过 ✅ 可上传 output/final.mp4 (+ final.srt / thumbnail.jpg)")


# ---------------- wechat_video (竖屏图文成片) ----------------


def _find_images(proj: Path) -> list:
    """查找项目中的图片素材（去重后按文件名排序）。"""
    img_exts = ("*.jpg", "*.jpeg", "*.png", "*.webp")
    candidates = []
    for ext in img_exts:
        candidates.extend(proj.glob(ext))
    for sub in ("formatted_raphael", "assets"):
        d = proj / sub
        if d.exists():
            for ext in img_exts:
                candidates.extend(d.glob(ext))
    seen = {}
    for p in candidates:
        seen.setdefault(p.name.lower(), p)
    return sorted(seen.values(), key=lambda p: p.name)


def cmd_wechat_video(proj: Path, title: str = "", voice: str = None):
    """竖屏图文成片：文章 .md → TTS → 配图轮播 → 字幕 → 1080×1920 MP4"""
    font_name, font_path = find_cjk_font()
    # ---------- 1. 读文章 ----------
    mds = sorted(proj.glob("*.md"))
    if not mds:
        die(f"在 {proj} 中找不到 .md 文章文件")
    raw = mds[0].read_text(encoding="utf-8")
    # 去 YAML front matter
    body = re.sub(r"^---\n.*?\n---\n", "", raw, flags=re.DOTALL)
    # 提取标题
    if not title:
        m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        title = m.group(1).strip() if m else "无标题"
    # 去掉 markdown 标题标记后作为口播稿
    narration = re.sub(r"^#+\s+", "", body, flags=re.MULTILINE).strip()
    if not narration:
        die("文章正文为空")
    log(f"文章标题: {title}  |  正文 {len(narration)} 字")

    # ---------- 2. 找配图 ----------
    images = _find_images(proj)
    log(f"配图: {len(images)} 张")
    for img in images:
        log(f"  └ {img.name}")

    # ---------- 3. TTS ----------
    voice = voice if voice is not None else os.environ.get("CF_VOICE", "zh-CN-YunxiNeural")
    rate = "+0%"
    build_dir = proj / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    audio_mp3 = build_dir / "wechat_tts.mp3"
    audio_srt = build_dir / "wechat_srt.srt"

    log("正在生成 TTS 配音 + 字幕…")
    asyncio.run(_tts_one(narration, voice, rate, audio_mp3, audio_srt, "sentence"))
    dur = media_duration(audio_mp3)
    log(f"配音完成 ({dur:.1f}s)")

    # ---------- 4. 渲染竖屏片段 ----------
    w, h = 1080, 1920  # 竖屏
    merged = build_dir / "wechat_merged.mp4"

    if images:
        seg_dur = dur / len(images)
        # 极短图片保护
        if seg_dur < 0.8:
            log(f"每张图仅 {seg_dur:.1f}s，合并为一张长图")
            seg_dur = dur
            images = [images[0]]
        clip_paths = []
        for i, img_path in enumerate(images):
            clip_out = build_dir / f"wechat_clip_{i:02d}.mp4"
            clip_paths.append(clip_out)
            if clip_out.exists() and abs(media_duration(clip_out) - seg_dur) < 0.5:
                log(f"片段{i+1} 已渲染，跳过")
                continue
            frames = max(int(seg_dur * FPS), 2)
            # scale+cover → Ken Burns 缓推
            vf = (
                f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},"
                f"zoompan=z='if(eq(on,1),1,min(zoom+0.0003,1.12))':d={frames}"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":s={w}x{h}:fps={FPS},setsar=1"
            )
            run([
                "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
                "-t", f"{seg_dur:.3f}",
                "-filter_complex", f"[0:v]{vf}[v]",
                "-map", "[v]",
                "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
                "-pix_fmt", "yuv420p",
                "-shortest", str(clip_out),
            ])
            log(f"  片段{i+1}/{len(images)} ✅ ({seg_dur:.1f}s)")
        # concat 拼接（视频无音轨）
        concat_txt = build_dir / "wechat_concat.txt"
        concat_txt.write_text(
            "\n".join(f"file '{p.resolve()}'" for p in clip_paths),
            encoding="utf-8",
        )
        run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_txt),
            "-c", "copy",
            str(merged),
        ])
        log("视频片段已拼接")
    else:
        # 无配图 → 纯色背景 + 标题文字
        log("无配图，生成文字背景视频")
        # 单行标题，居中显示
        bg_filter = (
            f"color=s={w}x{h}:c=#1a1a2e:d={dur:.3f}:r={FPS}[bg];"
            f"[bg]drawtext="
            f"text='{title}':"
            f"fontcolor=white:fontsize=56:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:"
            f"fontfile={font_path}[v]"
        )
        run([
            "ffmpeg", "-y",
            "-filter_complex", bg_filter,
            "-map", "[v]",
            "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
            "-pix_fmt", "yuv420p", "-t", f"{dur:.3f}",
            str(merged),
        ])
        log("纯文字背景视频已生成")

    # ---------- 5. 烧录字幕 + 混入配音 ----------
    output_dir = proj / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    final = output_dir / "wechat_video.mp4"
    srt_esc = str(audio_srt.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    sub_filter = f"subtitles='{srt_esc}':force_style='{sub_style(font_name)}'"

    run([
        "ffmpeg", "-y", "-i", str(merged), "-i", str(audio_mp3),
        "-vf", sub_filter,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-shortest", str(final),
    ])
    log(f"✦ 竖屏图文成片: {final}")
    log(f"  分辨率 {w}×{h}  |  时长 {dur:.1f}s  |  配图 {len(images)} 张  |  字幕已烧录")


# ---------------- batch ----------------


def cmd_batch(proj_dirs: list):
    """批量模式：自动处理多个项目，无人值守。一个失败不影响后续。"""
    total = len(proj_dirs)
    ok = fail = 0
    results = []

    log(f"批量模式启动，共 {total} 个项目\n" + "=" * 40)

    for idx, proj_path in enumerate(proj_dirs, 1):
        proj = Path(proj_path)
        label = proj.name
        print(f"\n[{idx}/{total}] 正在处理 {label}...", end=" ", flush=True)

        if not (proj / "project.yaml").exists():
            print("[FAILED] 缺少 project.yaml", flush=True)
            fail += 1
            results.append((label, "failed", "缺少 project.yaml"))
            continue

        try:
            load_env(proj)
            cmd_all(proj)
            print("[OK]", flush=True)
            ok += 1
            results.append((label, "ok", ""))
        except SystemExit as e:
            print(f"[FAILED] (exit code {e.code})", flush=True)
            fail += 1
            results.append((label, "failed", f"exit {e.code}"))
        except Exception as e:
            print(f"[FAILED] ({e})", flush=True)
            fail += 1
            results.append((label, "failed", str(e)))

    # 摘要
    print("\n" + "=" * 40)
    print(f"批量处理完成: {ok} 个成功, {fail} 个失败 (共 {total} 个项目)")
    if fail > 0:
        print("\n失败项目:")
        for label, status, reason in results:
            if status == "failed":
                print(f"  ❌ {label}: {reason}")
    log("批量模式结束")


# ---------------- clean / all ----------------

def cmd_clean(proj: Path):
    shutil.rmtree(proj / "build", ignore_errors=True)
    (proj / "build").mkdir(exist_ok=True)
    log("build 已清空(音频与素材保留,manifest 已重置)")


def cmd_all(proj: Path):
    cmd_tts(proj)
    cmd_assets(proj)
    cmd_subs(proj)
    cmd_render(proj)
    cmd_check(proj)


# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser(description="ClipForge — AI 全自动剪辑流水线")
    sub = ap.add_subparsers(dest="command")

    # 单项目命令
    for cmd in ["init", "tts", "assets", "subs", "render", "check", "all", "clean"]:
        p = sub.add_parser(cmd)
        p.add_argument("project", help="项目目录")

    # wechat_video 竖屏图文成片
    wp = sub.add_parser("wechat_video", help="竖屏图文成片（视频号）")
    wp.add_argument("project", help="项目目录（内含 .md 文章 + 配图）")
    wp.add_argument("--title", default="", help="文章标题（可选，默认从 markdown 提取）")
    wp.add_argument("--voice", default=None, help="配音音色（默认 CF_VOICE 或 zh-CN-YunxiNeural）")

    # 批量命令（支持多个项目目录或一个 topics.json）
    bp = sub.add_parser("batch", help="批量处理多个项目（无人值守）")
    bp.add_argument("projects", nargs="+",
                    help="项目目录（可传多个），或传入一个 topics.json 文件")

    args = ap.parse_args()

    if args.command == "batch":
        # 检测是否传入单个 JSON 文件
        if len(args.projects) == 1 and args.projects[0].endswith(".json"):
            with open(args.projects[0], encoding="utf-8") as f:
                topics = json.load(f)
            proj_dirs = [t["project_dir"] for t in topics]
        else:
            proj_dirs = args.projects
        cmd_batch(proj_dirs)
        return

    proj = Path(args.project)
    load_env(proj)
    if args.command != "init" and not shutil.which("ffmpeg"):
        die("未找到 ffmpeg,请先安装")

    dispatch = {"init": cmd_init, "tts": cmd_tts, "assets": cmd_assets,
                "subs": cmd_subs, "render": cmd_render, "check": cmd_check,
                "all": cmd_all, "clean": cmd_clean}

    if args.command == "wechat_video":
        cmd_wechat_video(proj, title=args.title, voice=args.voice)
    else:
        dispatch[args.command](proj)


if __name__ == "__main__":
    main()
