# ClipForge 视频脚本 SOP（SKILL.md for CC）

> 用途：CC 按本 SOP 产出 project.yaml（口播脚本 + 素材关键词一体），ClipForge 据此搜免费素材并用 FFmpeg 合成可上传 YouTube 的成片。
> 核心原则：**关键词在写脚本时产出，不依赖事后 LLM 提取。** 写脚本的人最清楚每个 scene 该配什么画面。

---

## 1. 视频结构模板

每个视频固定四段结构：

| 段落 | 时长 | 作用 | Scene 数 |
|------|------|------|----------|
| Hook | 0–8s | 前 5 秒留住人，抛出悬念/反常识结论 | 1 |
| Setup | 8–25s | 交代问题背景，建立"为什么值得看下去" | 1–2 |
| Body | 25s–N | 主体内容，每个要点 2–3 个 scene | 6–15 |
| CTA | 最后 10s | 总结一句话 + 订阅引导 | 1 |

- 目标总时长：5–8 分钟（YouTube 中视频，广告分成友好）
- Hook 禁止用 "In this video I will..." 开头，直接抛结论或反问

## 2. Scene 拆分规则

- **一个 scene = 一个视觉画面 = 8–15 秒口播**（约 20–40 个英文词）
- 拆分标准：口播内容换了一个"可视化的意象"，就必须换 scene
- 单个 scene 口播超过 15 秒 → 强制拆成两个，各自配不同 keywords
- 全片 scene 数参考：6 分钟视频 ≈ 28–40 个 scene

## 3. 口播文字（narration）写作规则

TTS（edge-tts）友好性：

1. 短句优先，一句不超过 20 个词
2. 数字写成朗读形式：`$1,000,000` → `one million dollars`；`5%` → `five percent`
3. 不用缩写和符号：`&` → `and`，`e.g.` → `for example`
4. 需要停顿处用句号，不靠逗号（TTS 对句号停顿更自然）
5. 语气：第二人称对话感（"you"），不用学术腔

## 4. 素材关键词（keywords）写作规则 ⭐ 核心

### 4.1 公式
keywords = 具体视觉名词 + 动作/场景修饰

- **2–3 个英文词**，全小写
- 必须是"摄像机能拍到的东西"，不能是抽象概念
- 想象你是 Pexels 的摄影师给视频打标签，你会打什么词？

### 4.2 必填字段：主关键词 + 2 组备选

每个 scene 必须给 3 组候选，ClipForge 按顺序回退：
```yaml
keywords: "man counting cash"
keywords_fallback:
  - "money stack table"
  - "wallet open hands"
```

备选规则：语义相近但**用词不同**（换名词，不是换形容词），保证搜索结果集不重叠。

### 4.3 禁用词表（写进"禁止重犯"）

以下抽象词在免费素材站几乎搜不到可用结果，**禁止单独作为 keywords**：
success, growth, wealth, freedom, mindset, motivation, discipline,
strategy, value, opportunity, potential, future, journey, passion,
inflation, economy, investment(单独用), habit, principle

抽象概念必须翻译成具体画面：

| 口播内容（抽象） | ❌ 坏关键词 | ✅ 好关键词 |
|------|------|------|
| 复利的力量 | compound interest | coins stacking timelapse |
| 通货膨胀侵蚀财富 | inflation | grocery price tag / burning money |
| 坚持自律 | discipline | man running sunrise / alarm clock morning |
| 财务自由 | financial freedom | beach laptop working / man mountain top |
| 时间比金钱重要 | time value | hourglass sand closeup / clock hands macro |
| 大多数人失败了 | failure | crowd walking street / man head down desk |

### 4.4 镜头元数据（可选，提升质感）
```yaml
shot_hint: "aerial"        # aerial / closeup / timelapse / slowmotion / macro
mood: "dark"               # dark / warm / energetic / calm
```

ClipForge 可将 shot_hint 拼进搜索词（"aerial city night"），mood 用于后期调色 LUT 选择。

## 5. project.yaml 完整 Schema

```yaml
project:
  title: "5 Money Habits Keeping You Poor"
  niche: "personal_finance"
  target_duration: 360          # 秒
  voice: "en-US-ChristopherNeural"
  bgm: "dark_ambient_01.mp3"
  bgm_volume: 0.12              # BGM 相对人声音量

scenes:
  - id: 1
    section: "hook"
    narration: >
      You are not poor because you earn too little.
      You are poor because of five habits you repeat every single day.
    keywords: "man empty wallet"
    keywords_fallback:
      - "counting coins table"
      - "worried man bills"
    shot_hint: "closeup"
    mood: "dark"

  - id: 2
    section: "setup"
    narration: >
      Most people never notice these habits.
      They feel normal. They feel harmless.
      But over ten years, they quietly drain hundreds of thousands of dollars.
    keywords: "crowd walking city"
    keywords_fallback:
      - "people commuting street"
      - "busy sidewalk timelapse"
    shot_hint: "slowmotion"
    mood: "dark"

  - id: 3
    section: "body"
    narration: >
      Habit number one. Buying things to impress people you do not even like.
      That new car loses twenty percent of its value the moment you drive it home.
    keywords: "luxury car showroom"
    keywords_fallback:
      - "new car keys handover"
      - "sports car driving city"
    shot_hint: "closeup"
    mood: "energetic"

  # ... 中间 scene 省略 ...

  - id: 32
    section: "cta"
    narration: >
      Fix one habit this week. Just one.
      Subscribe if you want your money to finally work for you.
    keywords: "sunrise city skyline"
    keywords_fallback:
      - "man walking sunrise"
      - "golden hour aerial city"
    shot_hint: "aerial"
    mood: "warm"
```

## 6. ClipForge 侧改进建议（工程项）

1. **搜索回退链**：keywords → fallback[0] → fallback[1] → DeepSeek 从 narration 提取 → "abstract background"
2. **质量过滤**：分辨率 ≥ 1920×1080；横屏；clip 原始时长 ≥ scene 音频时长
3. **全片去重**：维护已用 clip ID 集合
4. **多源搜索**：Pexels + Pixabay 并行搜
5. **时长对齐**：scene 时长 = TTS 音频实际时长 + 0.3s padding
6. **转场**：相邻 scene 用 0.3s crossfade

## 7. CC 输出前自检清单

- [ ] Hook 前 5 秒有反常识结论或悬念，无 "In this video"
- [ ] 每个 scene 口播 ≤ 15 秒（≤ 40 词）
- [ ] 每个 scene 有 keywords + 2 组 fallback，且三组名词不同
- [ ] 所有 keywords 无禁用抽象词
- [ ] 数字、符号已转为朗读形式
- [ ] 全片 keywords 无重复
- [ ] yaml 可被解析

## 8. 禁止重犯

1. keywords 用抽象名词 → 搜索 0 结果掉兜底
2. 单 scene 口播过长 → 素材 loop 超 2 次
3. 相邻 scene keywords 太相似 → 搜到同一素材被去重
