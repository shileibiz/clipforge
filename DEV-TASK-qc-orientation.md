# 任务：修复成片视频轨时长不足 + orientation 硬编码 + QC 视频轨校验

## 背景（clip-matcher Part A review 实测发现的存量 bug）

1. **视频素材时长 < 场景口播时长时，render 用 `-shortest` 兜底**：成片视频轨提前结束（实测某 56s 口播项目视频轨只有 21.87s，后面黑屏），而 QC 只查容器时长照样放行。
2. **clipforge.py 291/315/340 三处**（Pexels 视频 / Pexels 图片 / Pixabay+Unsplash）请求参数硬编码 `"orientation": "landscape"`，project.yaml 的 `orientation: portrait` 名存实亡（只有 scene_size() 正确跟随）。
3. **cmd_check 缺视频轨校验**：ffprobe 只看容器时长，没有分别校验视频流/音频流时长与期望时间轴（timeline.json）的偏差。

## 修复要求

1. **素材时长兜底（只许在 cmd_assets 兜底链函数内改，不动调用方）**：
   - 搜索结果里有 duration 字段（Pexels/Pixabay 视频都有）：优先选 duration ≥ 场景时长的素材；
   - 找不到足够长素材时，渲染该场景 clip 时用 `ffmpeg -stream_loop`（视频循环）或同类手段保证场景 clip 视频轨覆盖全场景时长；
   - 禁止让 `-shortest` 掩盖视频轨不足；图片 Ken Burns 路径不受影响。
2. **orientation 透传**：三处硬编码改为读取 project.yaml 的 orientation（landscape→landscape / portrait→portrait）；portrait 时视频搜 portrait、图片搜 portrait。默认仍 landscape。
3. **QC 增强（cmd_check）**：分别 ffprobe final.mp4 的视频流与音频流时长，与期望时间轴（check 已读 timeline.json）对比，任一轨 |Δ|>1.5s 即 fail（fail-fast，符合 SOP.md §4 故障表口径，故障表加一行处置提示）。
4. **回归测试**（仓库目前无 tests/，新建 tests/ 用 pytest 写）：
   - 测试A：构造视频素材短于场景时长的 fixture，断言渲染出的场景 clip 视频流时长 == 场景时长（允许 ±0.5s）；
   - 测试B：project.yaml `orientation: portrait` 时，三处素材搜索发出的请求参数里 orientation==portrait（mock requests 即可，不发真请求）。
   - 本机 PEP 668：装 pytest 用 `python3 -m venv /tmp/cfvenv && /tmp/cfvenv/bin/pip install pytest pyyaml requests edge-tts` 跑。
5. **真实端到端验证**（不许只跑单测）：
   - 用最小 project（可新建 /tmp 下 2 场景工程，口播 2 段各 3s，TTS 可 mock 音频）真实跑 render+check；
   - 再手动造一个视频轨不足的坏成片（或截断某场景 clip），确认新 QC 能拦（exit 非 0 且报视频轨时长差）。
6. **规约（CLAUDE.md 强约束）**：不改渲染编码参数（1080p/30fps/CRF20/yuv420p）；不动素材兜底链结构，只改链内函数；行为变化在 ROADMAP.md 记一行。

## 完成定义

全量 pytest 绿 + 端到端两步验证（正常成片过 QC、坏成片被拦）+ ROADMAP.md 更新 + `git add -A && git commit`（消息前缀 `fix:`）。**不要 push，等 review。**
