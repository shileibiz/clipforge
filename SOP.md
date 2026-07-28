# ClipForge SOP — AI 全自动视频剪辑标准作业流程

> 执行者: Claude Code (以下简称 CC)。人类只做两件事:给选题、看成片。
> 对应旧人工流程:写稿→录音→找无版权素材→剪辑拼接→做字幕→检查→上传。
> 现在全部由 CC 调用 `clipforge.py` 完成，人只在 Gate 处介入。

---

## 0. 前置条件（一次性）

1. `pip install edge-tts requests pyyaml`，系统装好 `ffmpeg`
2. 项目根目录放 `.env`（参考 `.env.example`）:
   - `PEXELS_API_KEY`（免费申请，主素材源，视频+图片）
   - `PIXABAY_API_KEY`（免费，视频兜底源）
   - `COVERR_API_KEY`（可选，高质量 B-roll 视频）
   - `UNSPLASH_ACCESS_KEY`（可选，顶级摄影图片源）
   - `DEEPSEEK_API_KEY`（可选，自动提取英文搜索词）
   - `COMFYUI_API`（可选，本地生图终极兜底，对接你 4060 上的 ComfyUI HTTP API）
3. 字幕字体: Linux 需要 `Noto Sans CJK SC`（`apt install fonts-noto-cjk`）

---

## 1. 流水线总览

一条命令跑全程: `python clipforge.py all <项目目录>`
每个阶段幂等可断点重跑: 已完成的场景自动跳过，失败即 fail-fast 并打印原因。

```
选题 → [CC写稿+分场景] → project.yaml
      → tts     (edge-tts 逐场景合成语音, 记录精确时长 → manifest.json)
      → assets  (Pexels视频 → Coverr视频 → Pixabay视频 → Pexels图片 → Unsplash图片 → ComfyUI生图, 六级兜底, 去重)
      → subs    (逐场景SRT按时长偏移合并为全片 final.srt)
      → render  (FFmpeg: 视频裁切1080p / 图片Ken Burns → 逐场景带音轨渲染 → concat → 烧字幕 + BGM池随机选曲混音)
      → check   (ffprobe QC: 时长差<1.5s、分辨率、音轨、srt/credits 齐全)
      → output/final.mp4 + final.srt + thumbnail.jpg + assets/credits.md
```

**命令速查:**

| 命令 | 功能 |
|------|------|
| `clipforge.py init <proj>` | 生成项目脚手架与 project.yaml 模板 |
| `clipforge.py tts <proj>` | edge-tts 逐场景配音，记录精确时长到 manifest |
| `clipforge.py assets <proj>` | 六级素材兜底链搜索下载，自动去重+来源记录 |
| `clipforge.py subs <proj>` | 逐场景 SRT 按时长偏移合并为全片字幕 |
| `clipforge.py render <proj>` | FFmpeg 渲染 + concat + 烧字幕 + BGM 池随机选曲混音 |
| `clipforge.py check <proj>` | QC: 时长/分辨率/音轨校验，产出 qc_report.json |
| `clipforge.py all <proj>` | 按序全跑（幂等，可断点续跑） |
| `clipforge.py clean <proj>` | 清空 build（保留音频与素材） |

---

## 2. CC 执行步骤

### Step 1 — 写稿并结构化（CC 生成 project.yaml）

#### 1a. 初始化项目

```bash
python clipforge.py init projects/<slug>
```

或通过 TubeForge 自动生成:

```bash
tube-forge run "你的选题" -o projects/<slug>/project.yaml
```

编辑 `project.yaml`，按以下规则填写 scenes。

---

#### 1b. 视频结构框架（CC 写稿必须遵守）

每个视频按以下时间轴结构组织场景:

```
┌─────────┬──────────┬───────────────┬──────────┐
│  Hook   │  Setup   │     Body      │   CTA    │
│  0-8s   │  8-25s   │  25s ~ N      │ 最后10s  │
│ 抓注意力 │ 抛出问题  │ 展开论述+N个  │ 引导互动 │
│         │  交代背景  │  论据/案例    │ 关注/点赞│
└─────────┴──────────┴───────────────┴──────────┘
```

- **Hook（前 8 秒）:** 用悬念句/反常识数据/尖锐问题开场，让观众停下来。必须在前 5 秒内出现视觉或听觉悬念。
- **Setup（8-25 秒）:** 交代视频要解决什么问题、为什么对观众重要。1-2 个场景。
- **Body（25 秒以后）:** 展开论述，每个论点 1-3 个场景。按「观点 → 例证 → 画面」循环推进。
- **CTA（最后 10 秒）:** 引导互动（点赞/关注/评论/下期预告）。

**目标成片时长:** 可灵活设定，常见档位:

| 目标时长 | 推荐场景数 | 平台适配 |
|---------|-----------|---------|
| 2~3 分钟 | 10~16 场景 | YouTube Shorts 高频资讯 |
| 4~6 分钟 | 18~28 场景 | YouTube 标准信息流 |
| 7~10 分钟 | 28~45 场景 | YouTube 深度科普/教程 |
| 15~20 分钟 | 50~80 场景 | B站 深度长视频 |

> 每个 scene = 一个视觉画面 = 一段连续口播（8~15 秒）。6 分钟 ≈ 28~40 scenes。
> 中文口播约 20~60 字 = 8~15 秒（正常语速 ~3.5 字/秒，含停顿）。
> **严禁**一个场景塞超过 80 字口播。

---

#### 1c. 每场景字段规范

每 scene 的 YAML 字段（★=必填，☆=可选）:

```yaml
scenes:
  - text: "口播文案"                           # ★ 20~60字，一句完
    keywords: [keyword1, keyword2, keyword3]   # ★ 见下方关键词规则
    asset_type: video                          # ☆ video/image/auto，默认 auto
    voice: zh-CN-YunxiNeural                   # ☆ 本场景独立声线（覆盖全局）
    rate: "+8%"                                # ☆ 本场景独立语速（覆盖全局）
```

**代码实际使用的字段**（不存在于代码中的字段会被忽略）:

| 字段 | 在代码中使用位置 | 说明 |
|------|-----------------|------|
| `text` | `cmd_tts()` → edge-tts 配音 | 口播文案 |
| `keywords` | `cmd_assets()` → 遍历列表逐关键词搜素材 | 搜索关键词（见下方规则） |
| `asset_type` | `cmd_assets()` → 决定搜 video/image/auto | 素材偏好 |
| `voice` | `cmd_tts()` → 单场景覆盖全局 voice | 可选 |
| `rate` | `cmd_tts()` → 单场景覆盖全局 rate | 可选 |

---

#### 1d. 关键词规则（核心！最容易犯错）

每个 scene **必须给 3 个英文关键词**（代码会按顺序逐个尝试搜素材，直到命中）:

```yaml
keywords: [计算机键盘特写, 手指打字, 程序员工作台]
```

**三层搜索机制:** 代码拿到 `keywords` 列表后，对每个关键词依次调用六级素材兜底链。
第一个命中任意素材源的关键词即被采用，后续不继续搜。
所以**第 1 个关键词最重要**，应是最精确、最可能搜到好素材的词。

**黄金规则:**

| 规则 | ❌ 禁止 | ✅ 推荐 |
|------|---------|--------|
| 具体视觉名词 | `success`, `growth`, `wealth`, `freedom`, `mindset` | `coins stacking timelapse`, `stock chart green`, `handshake business` |
| 抽象→具体转换 | `复利的力量` | `coins stacking timelapse` |
| 全小写英文 | `Stock_Chart` | `stock chart` |
| 名词性短语 | `growing money` | `money growth`, `investment portfolio` |
| Pexels 友好 | `abstract future concept` | `city skyline sunset`, `mountain lake reflection` |
| 相邻场景差异化 | 场景1=`sunset beach`, 场景2=`sunset ocean` | 场景1=`sunset beach`, 场景2=`stock market chart` |

**抽象概念具体化对照表（常见场景）:**

| 抽象概念 | 应翻译成 |
|----------|---------|
| 复利/增长 | `coins stacking timelapse`, `snowball rolling`, `plant growing time lapse` |
| 风险管理 | `insurance document signing`, `umbrella in rain`, `safety net` |
| 被动收入 | `sleeping person`, `bank account app`, `rental property keys` |
| 长期主义 | `tree growing`, `climbing mountain`, `marathon runner` |
| 科技/AI | `robot arm assembly`, `server rack lights`, `neural network animation` |
| 个人成长 | `bookshelf library`, `graduation cap`, `training gym` |
| 理财投资 | `stock chart`, `calculator coins`, `investment portfolio document` |
| 心态/坚持 | `mountain climber`, `sunrise ocean`, `exercise repetition` |

**为什么必须 3 个关键词？**

1. 第 1 个关键词是最佳匹配 → 精准搜到最好
2. 第 2/3 个是 fallback → Pexels/Pixabay 可能对某些词无结果
3. 相邻场景关键词必须差异大 → 避免两场景用同一素材（代码有 id 去重，但尽量源头避免）

---

#### 1e. TTS 友好写作规则

因为 edge-tts 是机器配音，以下写法确保朗读自然:

| 规则 | ❌ 不好 | ✅ 好 |
|------|---------|-------|
| 短句优先 | 「复利作为一种金融现象…」 | 「什么是复利？简单说就是利滚利。」 |
| 数字写为朗读形式 | 「99% 的人在 50 岁后…」 | 「百分之九十九的人在五十岁后才…」 |
| 不用缩写 | 「AI 虽好但 ROI 不明」 | 「人工智能虽好但投资回报率不明」 |
| 避免同音歧义 | 「期中期权」 | 「期货中的期权」 |
| 问句引导 | 「复利很重要」 | 「复利到底有多重要？」 |

---

### Step 2 — 自动执行

```bash
python clipforge.py all projects/<slug>
```

CC 观察输出，任一阶段失败按 §4 处置后重跑同一条命令（幂等续跑）。

### Step 3 — QC 与交付

- `check` 通过后，产物在 `output/`: `final.mp4`、`final.srt`（软字幕备用）、`thumbnail.jpg`
- CC 汇报: 成片时长、场景数、素材来源统计（credits.md）、QC 报告路径

**🚪 Gate 2（必过）:** 人工看一遍成片（重点: 素材与文案是否语义错位、字幕断句）。
通过 → 上传 YouTube/B站；不通过 → 只改问题场景的 keywords 或 text，删掉对应
`assets/scene_XX.*`、`build/clip_XX.mp4` 与 manifest 中该场景的 `asset_ok`，重跑 `all`。

---

## 3. CC 自检清单（提交前逐一核查）

在把 `project.yaml` 提交给 ClipForge 之前，逐项确认:

- [ ] **Hook 前 5 秒有悬念:** 不能是平平无奇的陈述句开场
- [ ] **每 scene 口播 ≤ 60 字:** 超过则拆分场景
- [ ] **每个 scene 有 3 个 keywords:** 不要少于 3
- [ ] **keywords 无抽象词:** 没有 success/growth/wealth/freedom/mindset 等
- [ ] **抽象概念已翻译成具体画面:** 参照 §1d 对照表
- [ ] **相邻 scene keywords 差异明显:** 不要高度相似
- [ ] **全小写英文:** 没有大写、没有中文
- [ ] **数字已转朗读形式:** `99%` → `百分之九十九`
- [ ] **无缩写:** 没有 ROI/USA/WTF 等
- [ ] **YAML 缩进正确:** scenes 缩进 2 格，keywords 缩进 4 格
- [ ] **全片口播总时长约合目标时长:** 总字数 ÷ 3.5 ≈ 秒数

---

## 4. 故障处置表（CC 按表自愈，不要瞎猜）

| 症状 | 原因 | 处置 |
|------|------|------|
| tts 阶段音频时长 < 0.5s | edge-tts 网络被墙/波动 | 走代理重跑；仍失败换 voice 重试一次 |
| assets 全源失败 | keywords 太抽象/中文 | 换更具体的英文名词性 keywords 重跑 assets。已有 6 个免费源，全失败概率极低 |
| Pexels 429 | 免费额度 200次/小时 | sleep 后重跑，Coverr/Pixabay 会自动兜底 |
| Coverr/Unsplash 无结果 | 关键词过偏 | 不影响其他源正常兜底 |
| 字幕乱码/方框 | 缺 CJK 字体 | `apt install fonts-noto-cjk` 或改用 WenQuanYi |
| duration_delta > 1.5s | 某场景 clip 渲染截断 | 删对应 build/clip_XX.mp4 重跑 render |
| 竖版需求（抖音/Shorts） | — | project.yaml 设 `orientation: portrait` |
| 某场景素材与口播语义错位 | keywords 选词不当 | 改该场景 keywords → 删对应 assets/scene_XX.* + manifest 中该场景 asset_ok → 重跑 all |

---

## 5. 禁止重犯（错误一次，规则一条）

1. **keywords 用抽象词:** keywords 必须全小写英文、名词性、具体视觉画面；禁止 `success`/`growth`/`wealth`/`freedom`/`mindset` 等。
2. **单 scene 口播过长:** 60 字上限（中文），超了必须拆场景。
3. **相邻 scene keywords 太相似:** 强制在不同场景用不同的视觉主题。
4. **同一素材 id 全片复用:** 工具已内置去重，但 CC 写 keywords 时也应主动避免。
5. **手动改 manifest.json 时长字段:** 时长以 ffprobe 为准，禁止手改。
6. **上传前 credits.md 缺失:** assets/credits.md 必须存在（素材可溯源是底线）。
7. **失败绕过 QC:** 失败即停（fail-fast），按故障表处置后重跑同一命令，禁止跳过 check。
8. **改编码参数:** 1080p/30fps/CRF20/yuv420p 是平台兼容性底线，禁止随意改。
9. **中文场景用 word 字幕模式:** `subtitle_mode: word` 仅英文启用，中文默认 `sentence`。
10. **每次踩坑不记:** 每次踩坑，把规则写进本表，再改代码。

---

## 6. project.yaml 完整字段参考

### 顶层字段

```yaml
title: "视频标题"                          # ★ 仅用于人识别，代码不用
voice: zh-CN-YunxiNeural                  # ☆ edge-tts 声音 ID，默认 zh-CN-YunxiNeural
rate: "+8%"                               # ☆ 语速微调，默认 +0%
subtitle_mode: sentence                   # ☆ sentence(中文推荐)/word(英文推荐)
bgm: "music/upbeat.mp3"                   # ☆ 单文件 BGM（与 bgm_pool 二选一，bgm_pool 优先）
bgm_volume: 0.12                          # ☆ BGM 音量倍率，默认 0.12 (12%)
bgm_pool:                                 # ☆ BGM 池（优先于 bgm）
  - path: music/upbeat.mp3
    tags: [轻松, 励志, 科技感]
  - path: music/cinematic.mp3
    tags: [科技感, 震撼]
orientation: landscape                    # ☆ landscape(1920x1080) / portrait(1080x1920)
```

### scenes 字段

```yaml
scenes:
  - text: "口播文案，20~60字"               # ★ 必填
    keywords: [keyword1, keyword2, keyword3] # ★ 必填，3 个英文关键词
    asset_type: video                       # ☆ video/image/auto，默认 auto
    voice: zh-CN-YunxiNeural                # ☆ 可选，覆盖全局 voice
    rate: "+8%"                             # ☆ 可选，覆盖全局 rate
```

### 不支持的字段（如果 CC 在脚本编写中使用，需要先改代码）

| 字段 | 状态 | 说明 |
|------|------|------|
| `shot_hint` | ❌ 不支持 | 无代码实现；当前素材搜索仅依赖 `keywords` |
| `mood` | ❌ 不支持 | 无代码实现；当前不按情绪选择素材 |
| `keywords_fallback` | ❌ 不需要 | 代码对 `keywords` 数组按顺序逐词尝试搜索，第一个命中即停。所以在 SOP 层面要求 CC 写 3 个 keywords，第 1 个最佳、后 2 个 fallback，即可实现同样效果，无需单独字段 |

> **设计说明:** ClipForge 对 `keywords` 的处理逻辑是从数组第 0 个开始，遍历每个关键词、
> 逐级尝试 6 个素材源。第 1 个命中任意源的词即被采用。所以 keywords[0] = 最佳匹配、
> keywords[1] = 第一 fallback、keywords[2] = 第二 fallback。CC 在写稿时按此顺序排列即可，
> 不需要在 YAML 中增加 `keywords_fallback` 字段。

---

## 7. 与 TubeForge 的上下游关系

- **TubeForge**（`/home/mark/tube_forge/tube_forge.py`）: 选题 → DeepSeek 写稿 → 分场景 → 产出 ClipForge 兼容 project.yaml
- ClipForge 是 TubeForge 的"渲染引擎层"。单命令全流程: `tube-forge run "选题" -o proj/project.yaml && clipforge.py all proj`
- TubeForge 的 system prompt 已包含 keywords 规则，CC 若直接写 project.yaml 也需遵守同一套规则

---

## 8. BGM 素材库

项目 `/home/mark/clipforge/music/` 已有 **67 首免费 MP3**（来自 Mixkit）:

| 分类 | 数量 | 大小 | 推荐标签 |
|:-----|:----:|:----:|:---------|
| `upbeat/` | 14 | 51M | 轻快、励志、积极 |
| `cinematic/` | 12 | 39M | 科技感、震撼、Corporate |
| `chill/` | 41 | 174M | 轻松、背景、Ambient、Lo-Fi |

BGM 素材需**手动从免费音乐站下载**（pixabay.com/music、mixkit.co、uppbeat.io），存到 `music/` 目录。
推荐一次性下载 20-30 首按标签分类，永久复用。

---

## 9. 竖版视频（Shorts/抖音）

`project.yaml` 设 `orientation: portrait` 即输出 1080x1920。

竖版视频注意事项:
- 场景数建议减少 20-30%（竖版信息密度更高）
- keywords 可考虑加 `vertical video`、`tiktok style` 等限定词
- 字幕 style 的 MarginV 可能需要调整（当前未针对竖版优化）
