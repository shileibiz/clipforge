# 免费无版权素材 API 调研 — ClipForge 集成推荐

## 一、现有架构分析

ClipForge 当前素材兜底链（`cmd_assets` 的 `for kw` 循环内）：

```
pexels_video(kw, used) → pixabay_video(kw, used) → pexels_photo(kw, used) → comfyui_image(prompt, out)
```

每个 provider 函数签名统一：`fn(keyword: str, used: set) -> dict | None`
返回 dict 格式：
```python
{"kind": "video"/"image", "url": "直接下载URL", "id": "去重id", "ext": ".mp4/.jpg", "credit": "来源声明"}
```

新增 provider 只需写一个新函数，在 `cmd_assets` 的兜底链中插入一行，**不改架构**。

---

## 二、候选 API 全息表

### 2.1 视频素材 API

| API | 是否需要 Key | 免费额度 | 搜索质量 | HTTPS 直链 | 许可证 |
|-----|-------------|----------|---------|-----------|--------|
| **Pexels** ✅ 已有 | 是 | 200 req/min | ⭐⭐⭐⭐⭐ 画面感强 | ✅ 直链 .mp4 | 免版权可商用 |
| **Pixabay** ✅ 已有 | 是 | 100 req/60s | ⭐⭐⭐⭐ 量大质中 | ✅ 直链 .mp4 | CC0/免版权 |
| **Coverr** ⭐ 强烈推荐 | **需要** API Key | Staging: 50 calls/h (≈1000/月), Production: 2000 calls/h | ⭐⭐⭐⭐⭐ 高质量电影感 | ✅ 直链 | 免版权可商用 |
| **Mixkit** ❌ 无 API | — | 无程序化接口，只能手动下载 | ⭐⭐⭐⭐ 质量不错 | 仅 Web | 免版权 |
| **Videvo** ❌ 无 API | — | 无公开 API（部分视频需付费） | ⭐⭐⭐ 中等 | 仅 Web | 混合（部分需署名） |
| **Mazwai** ❌ 无 API | — | 无 API | ⭐⭐⭐⭐ 精选电影感 | 仅 Web | 免版权 |
| **Videezy** ❌ 无 API | — | 无 API | ⭐⭐⭐ 中等 | 仅 Web | 混合 |
| **Pexels 视频** | 已有 | 200 req/min | ⭐⭐⭐⭐⭐ | ✅ | 免版权可商用 |

### 2.2 图片素材 API

| API | 是否需要 Key | 免费额度 | 搜索质量 | HTTPS 直链 | 许可证 |
|-----|-------------|----------|---------|-----------|--------|
| **Pexels 图片** ✅ 已有 | 是 | 200 req/min | ⭐⭐⭐⭐⭐ | ✅ | 免版权可商用 |
| **Unsplash** ⭐ 强烈推荐 | **需要** API Key | 免费: 50 req/h, 申请生产: 5000 req/h | ⭐⭐⭐⭐⭐ 顶级摄影 | ✅ 直链可调尺寸 | 免版权可商用(需署名) |
| **Pixabay 图片** ⭐ 推荐 | 已有 Key 即可复用 | 100 req/60s | ⭐⭐⭐⭐ | ✅ | CC0 无需署名 |
| **Openverse** ⭐ 推荐 | 可选（匿名也可用） | 无严格限制（throttle 保护） | ⭐⭐⭐ 质量参差（CC 聚合） | ✅ | CC0/CC 授权混合 |
| **Lorem Picsum** | **不需要** | 无限制 | ⭐⭐ 随机占位图 | ✅ | 无版权 |
| **Freepik/Magnific** | 需要 | 付费（$39/月起） | ⭐⭐⭐⭐⭐ | ✅ | 商业授权需要订阅 |

### 2.3 音频/音效/BGM API

| API | 是否需要 Key | 免费额度 | 素材类型 | HTTPS 直链 | 许可证 |
|-----|-------------|----------|---------|-----------|--------|
| **Freesound** ⭐ 推荐 | **需要** API Key | 30 req/min, 500 req/day | 音效/短音频 | ✅ | CC0/CC 混合 |
| **Pixabay Music** ⭐ 推荐 | **复用已有 Key** | 100 req/60s（同图片视频） | BGM/长音频 | ✅ 直链 .mp3 | 免版权可商用 |
| **Mixkit Music** ❌ 无 API | — | 无 API，仅 Web 下载 | BGM/长音频 | 仅 Web | 免版权可商用 |
| **Coverr Music** | 同 Coverr API | 同视频共享额度 | BGM/音效 | ✅ | 免版权可商用 |

---

## 三、各 API 详细评估

### 3.1 Coverr（最高推荐 — 视频 + 音乐）

- **API 地址**: https://coverr.co/developers
- **免费额度**: Staging 50 calls/h（开发测试），Production 2000 calls/h（申请后免费）
- **质量**: 电影级，画面感强，非常符合 YouTube/B站 B-roll 需求
- **直链下载**: ✅ 返回直接可下载的 .mp4 URL
- **集成难度**: 简单 REST API，支持搜索/分类/精选
- **优势**: 免费、高质量、支持视频+音乐双素材

### 3.2 Unsplash（图片首选）

- **API 地址**: https://unsplash.com/developers
- **免费额度**: 50 req/h（开发），申请 Production 后 5000 req/h
- **图片质量**: ⭐⭐⭐⭐⭐ 全球顶级摄影社区
- **直链下载**: ✅ URL 后可调 `w=1920` `q=80` 等参数
- **限制**: 需署名（`Photo by <Author> on Unsplash`），ClipForge 的 `credits.md` 已支持
- **SDK**: 官方 JavaScript/PHP/Ruby，社区 Python/Go 库

### 3.3 Openverse（开源 CC 素材聚合）

- **API 地址**: https://wordpress.github.io/openverse-api/
- **免费额度**: 匿名可用，有 throttle 保护
- **素材范围**: 6 亿+ CC 授权图片、音频、视频
- **质量**: 参差不齐（来源广泛），但胜在量大
- **认证**: 可选匿名或注册 client_id
- **适用场景**: 作为兜底源，在 Pexels/Unsplash 均无结果时使用

### 3.4 Freesound（音效）

- **API 地址**: https://freesound.org/docs/api/
- **免费额度**: 30 req/min, 500 req/day（写入操作更严）
- **素材**: 50 万+ 社区上传音效，短音频为主
- **直链下载**: ✅ `Download` 端点返回音频文件
- **适用**: 音效素材（非 BGM），适合丰富 ClipForge 的音频素材库

### 3.5 Pixabay 图片 + 音乐（低投入扩展）

- **API 地址**: https://pixabay.com/api/docs/
- **Key**: 复用已有 `PIXABAY_API_KEY`
- **免费额度**: 100 req/60s
- **内容**: 图片、插画、矢量图、音乐（!）、音效
- **注意事项**: Pixabay 的 API 文档显示图片和视频 endpoint 已验证。音乐 endpoint 也走相同 API，但可能特定地区限制，需实测确认直链下载可靠性。

---

## 四、推荐集成方案（3 个优先 + 2 个次选）

### 🔥 第一优先级（立即加）

| 顺序 | Provider | 类型 | 函数名 | 新增代码行数 | 理由 |
|------|---------|------|--------|------------|------|
| **1** | **Coverr 视频** | video | `coverr_video(kw, used)` | ~30 行 | 质量最高的免费视频 API，直链下载，填补 Pexels/Pixabay 之外的精选源 |
| **2** | **Unsplash 图片** | image | `unsplash_photo(kw, used)` | ~30 行 | 图片质量天花板，已有 Pexels 图片不够时可兜底 |
| **3** | **Pixabay 音乐** | audio (BGM) | `pixabay_music(kw)` | ~25 行 | 零成本（复用 Key），为 ClipForge 增加 BGM 素材源 |

### 🔄 第二优先级（稍后加）

| 顺序 | Provider | 类型 | 函数名 | 理由 |
|------|---------|------|--------|------|
| **4** | **Openverse 图片/视频** | image+video | `openverse_media(kw, used)` | 海量 CC 素材兜底，但质量需过滤 |
| **5** | **Freesound 音效** | audio (SFX) | `freesound_sfx(kw)` | 增加音效素材，丰富场景 |

---

## 五、具体实现指南

### 5.1 Coverr Video Provider（示例代码）

```python
def coverr_video(kw, used):
    """Coverr 免费视频搜索 — 高质量电影感 B-roll"""
    key = os.environ.get("COVERR_API_KEY")
    if not key:
        return None
    try:
        r = requests.get(
            "https://coverr.co/api/videos/search",  # 确认实际 endpoint
            headers={"Authorization": f"Bearer {key}"},
            params={"query": kw, "per_page": 8},
            timeout=30
        )
        for v in r.json().get("videos", []):
            vid = f"coverr-{v['id']}"
            if vid in used:
                continue
            # Coverr 返回的视频文件 URL
            url = v.get("video_files", [{}])[0].get("link") or v.get("url")
            if url:
                return {
                    "kind": "video",
                    "url": url,
                    "id": vid,
                    "ext": ".mp4",
                    "credit": f"Coverr video {v.get('page_url', '') or v.get('title', '')}"
                }
    except Exception as e:
        log(f"Coverr 视频搜索失败: {e}")
    return None
```

### 5.2 Unsplash Photo Provider（示例代码）

```python
def unsplash_photo(kw, used):
    """Unsplash 图片搜索 — 顶级摄影作品"""
    key = os.environ.get("UNSPLASH_API_KEY")
    if not key:
        return None
    try:
        r = requests.get(
            "https://api.unsplash.com/search/photos",
            headers={"Authorization": f"Client-ID {key}"},
            params={"query": kw, "per_page": 8, "orientation": "landscape"},
            timeout=30
        )
        for p in r.json().get("results", []):
            pid = f"unsplash-{p['id']}"
            if pid in used:
                continue
            # Unsplash URL 后加参数可控制尺寸
            url = p["urls"]["raw"] + "&w=1920&q=80&fit=crop"
            return {
                "kind": "image",
                "url": url,
                "id": pid,
                "ext": ".jpg",
                "credit": f"Photo by {p['user']['name']} on Unsplash ({p['links']['html']})"
            }
    except Exception as e:
        log(f"Unsplash 图片搜索失败: {e}")
    return None
```

### 5.3 Pixabay Music Provider（示例代码）

```python
def pixabay_music(kw):
    """Pixabay 免费音乐搜索（复用 PIXABAY_API_KEY）"""
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return None
    try:
        # Pixabay 音频 endpoint — 需确认具体 URL
        r = requests.get(
            "https://pixabay.com/api/audio/",
            params={"key": key, "q": kw, "per_page": 5},
            timeout=30
        )
        hits = r.json().get("hits", [])
        if hits:
            # 返回第一个匹配的音频
            a = hits[0]
            return {
                "kind": "audio",
                "url": a.get("url") or a.get("preview_url"),
                "id": f"pixabay-audio-{a['id']}",
                "ext": ".mp3",
                "credit": f"Pixabay music: {a.get('title', '')}"
            }
    except Exception as e:
        log(f"Pixabay 音乐搜索失败: {e}")
    return None
```

### 5.4 集成到 `cmd_assets`（只需改一行）

当前代码（第 377 行）：
```python
found = pexels_video(kw, used) or pixabay_video(kw, used)
```

改为：
```python
found = (pexels_video(kw, used) or coverr_video(kw, used)
         or pixabay_video(kw, used))
```

当前图片兜底（第 379 行）：
```python
found = pexels_photo(kw, used)
```

改为：
```python
found = pexels_photo(kw, used) or unsplash_photo(kw, used)
```

### 5.5 BGM 自动搜索（可选增强）

如果想为 `project.yaml` 的 `bgm` 字段添加自动搜索，可在 `cmd_init` 或 `cmd_assets` 后加一步：

```python
if not cfg.get("bgm"):
    bgm = pixabay_music("background music cinematic")
    if bgm:
        bgm_path = proj / "assets" / bgm["id"]
        download(bgm["url"], bgm_path)
        # 写入 project.yaml 或注入 manifest
```

### 5.6 环境变量新增

在 `clipforge.py` 头部 docstring 的环境变量说明和 `load_env` 中增加：

```
COVERR_API_KEY    可选   https://coverr.co/developers
UNSPLASH_API_KEY  可选   https://unsplash.com/developers
```

---

## 六、兜底链优先级建议（最终推荐顺序）

修改 `cmd_assets` 后新的兜底链：

```
# 视频
pexels_video(kw, used) → coverr_video(kw, used) → pixabay_video(kw, used)
# 图片（未找到视频时）
pexels_photo(kw, used) → unsplash_photo(kw, used)
# 本地兜底
comfyui_image(prompt, out)
# 最终
→ fail-fast
```

这条链保证：**从最快/最可靠的源开始试，逐级递降**。Pexels 速度最快放首位，Coverr 质量高放第二位兜底，Pixabay 量大放第三位。

---

## 七、不推荐的 API 及原因

| API | 不推荐原因 |
|-----|-----------|
| **Mixkit** | 无公开 API，仅 Web 手动下载，无法程序化集成 |
| **Videvo** | 无 API，部分素材需付费，许可混合 |
| **Mazwai** | 无 API，仅 Web |
| **Videezy** | 无 API，质量一般 |
| **Freepik/Magnific** | 付费 API，$39/月起，不适合完全免费的 ClipForge |
| **Epidemic Sound** | 付费订阅，$15/月，不适合免费方案 |
| **Lorem Picsum** | 纯随机占位图，不适合搜索具体 B-roll 素材 |

---

## 八、总结

### 立即可以加的 3 个源（零架构改动）

| 源 | 类型 | 难度 | 收益 |
|---|------|------|------|
| Coverr | 视频 ★新 | 低（~30 行代码 + API key） | 最缺的**高质量视频**源 |
| Unsplash | 图片 ★新 | 低（~30 行代码 + API key） | 顶级摄影图片补短板 |
| Pixabay Music | 音频 BGM ★新 | 最低（~25 行，复用已有 Key） | 增加自动 BGM 能力 |

### 后续可加的 2 个源

| 源 | 类型 | 难度 | 收益 |
|---|------|------|------|
| Openverse | 图片+视频 | 中（匿名可用，需结果过滤） | 6 亿+ CC 素材兜底 |
| Freesound | 音效 | 中（API key + 速率限制） | 增加场景音效 |

### 配置文件变更

只需在 `.env` 中新增两行（Key 为可选）：
```
COVERR_API_KEY=your_key_here
UNSPLASH_API_KEY=your_key_here
```

所有新增 provider 在 Key 不存在时自动跳过，**不影响现有用户**。
