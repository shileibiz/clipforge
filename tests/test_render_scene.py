"""测试A: 视频素材短于场景口播时长时, 场景 clip 视频轨仍覆盖全场景时长。"""
import shutil
import subprocess

import pytest

import clipforge

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="需要 ffmpeg")

SCENE_DUR = 6.0


def _ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


@pytest.fixture
def short_asset_proj(tmp_path):
    for d in ("assets", "audio", "build"):
        (tmp_path / d).mkdir()
    # 素材仅 1.5s, 口播 6s
    _ff("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25:d=1.5",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp_path / "assets" / "scene_01.mp4"))
    _ff("-f", "lavfi", "-i", f"sine=f=440:d={SCENE_DUR}",
        "-c:a", "libmp3lame", str(tmp_path / "audio" / "scene_01.mp3"))
    dur = clipforge.media_duration(tmp_path / "audio" / "scene_01.mp3")
    rec = {"asset": "assets/scene_01.mp4", "asset_kind": "video", "duration": dur}
    return tmp_path, rec


def test_short_video_asset_clip_covers_scene(short_asset_proj):
    proj, rec = short_asset_proj
    out = clipforge.render_scene(proj, {"orientation": "landscape"}, "01", rec)
    vdur = clipforge.stream_duration(out, "video")
    assert vdur == pytest.approx(rec["duration"], abs=0.5)
    assert clipforge.stream_duration(out, "audio") == pytest.approx(rec["duration"], abs=0.5)


def test_stale_clip_with_short_video_is_rerendered(short_asset_proj):
    """旧片段视频轨不足但容器时长(音轨)达标时, 不得被当成已渲染跳过。"""
    proj, rec = short_asset_proj
    stale = proj / "build" / "clip_01.mp4"
    _ff("-i", str(proj / "assets" / "scene_01.mp4"), "-i", str(proj / "audio" / "scene_01.mp3"),
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", str(stale))
    assert clipforge.media_duration(stale) == pytest.approx(rec["duration"], abs=0.5)
    assert clipforge.stream_duration(stale, "video") < 2.0
    out = clipforge.render_scene(proj, {}, "01", rec)
    assert clipforge.stream_duration(out, "video") == pytest.approx(rec["duration"], abs=0.5)


def test_pick_prefers_asset_long_enough():
    cands = [(3, "short"), (12, "long"), (20, "longer")]
    assert clipforge._pick_long_enough(cands, 8.0) == "long"
    # 都不够长 → 取最长, 交给 render 循环补足
    assert clipforge._pick_long_enough([(3, "a"), (5, "b"), (None, "c")], 8.0) == "b"
    assert clipforge._pick_long_enough([], 8.0) is None
