"""测试B: project.yaml orientation 透传到素材搜索请求参数 (mock requests, 不发真请求)。"""
from unittest import mock

import pytest
import yaml

import clipforge

URLS = {
    "pexels_video": "https://api.pexels.com/videos/search",
    "pexels_photo": "https://api.pexels.com/v1/search",
    "unsplash_photo": "https://api.unsplash.com/search/photos",
}


def _resp(payload):
    r = mock.Mock(status_code=200)
    r.json.return_value = payload
    return r


@pytest.fixture
def env(monkeypatch):
    for k in ("PEXELS_API_KEY", "UNSPLASH_ACCESS_KEY", "PIXABAY_API_KEY"):
        monkeypatch.setenv(k, "test-key")
    for k in ("COVERR_API_KEY", "COMFYUI_API"):
        monkeypatch.delenv(k, raising=False)


def _make_proj(tmp_path, orientation):
    cfg = {"title": "t", "scenes": [{"text": "测试场景。", "keywords": ["city"],
                                     "asset_type": "auto"}]}
    if orientation:
        cfg["orientation"] = orientation
    (tmp_path / "project.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True),
                                           encoding="utf-8")
    (tmp_path / "assets").mkdir()
    return tmp_path


def _orientations_sent(tmp_path, orientation):
    proj = _make_proj(tmp_path, orientation)
    with mock.patch.object(clipforge.requests, "get", return_value=_resp({})) as get:
        with pytest.raises(SystemExit):   # 全部无结果 + 无 ComfyUI → fail-fast
            clipforge.cmd_assets(proj)
    sent = {}
    for call in get.call_args_list:
        url = call.args[0]
        for name, u in URLS.items():
            if url == u:
                sent[name] = call.kwargs["params"].get("orientation")
    return sent


@pytest.mark.parametrize("orientation", ["portrait", "landscape"])
def test_orientation_passthrough(tmp_path, env, orientation):
    sent = _orientations_sent(tmp_path, orientation)
    assert sent == {name: orientation for name in URLS}


def test_orientation_defaults_to_landscape(tmp_path, env):
    sent = _orientations_sent(tmp_path, None)
    assert sent == {name: "landscape" for name in URLS}


def _pixabay_hit(vid, w, h, dur):
    return {"id": vid, "duration": dur, "pageURL": "",
            "videos": {"large": {"url": f"https://x/{vid}.mp4", "width": w, "height": h}}}


def test_pixabay_filters_by_orientation(env):
    """Pixabay 视频 API 无 orientation 参数, 按返回宽高本地过滤。"""
    hits = {"hits": [_pixabay_hit(1, 1920, 1080, 30), _pixabay_hit(2, 1080, 1920, 30)]}
    with mock.patch.object(clipforge.requests, "get", return_value=_resp(hits)):
        assert clipforge.pixabay_video("city", set(), "portrait")["id"] == "pixabay-v-2"
        assert clipforge.pixabay_video("city", set(), "landscape")["id"] == "pixabay-v-1"


def test_video_sources_prefer_long_enough(env):
    pexels = {"videos": [
        {"id": i, "duration": d, "url": f"https://p/{i}",
         "video_files": [{"width": 1920, "height": 1080, "link": f"https://p/{i}.mp4"}]}
        for i, d in ((1, 4), (2, 15), (3, 30))]}
    with mock.patch.object(clipforge.requests, "get", return_value=_resp(pexels)):
        assert clipforge.pexels_video("city", set(), min_dur=10.0)["id"] == "pexels-v-2"
        assert clipforge.pexels_video("city", set(), min_dur=60.0)["id"] == "pexels-v-3"
        assert clipforge.pexels_video("city", set())["id"] == "pexels-v-1"
    pixabay = {"hits": [_pixabay_hit(1, 1920, 1080, 5), _pixabay_hit(2, 1920, 1080, 20)]}
    with mock.patch.object(clipforge.requests, "get", return_value=_resp(pixabay)):
        assert clipforge.pixabay_video("city", set(), min_dur=10.0)["id"] == "pixabay-v-2"
