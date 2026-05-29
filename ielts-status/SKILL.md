---
name: ielts-status
description: |
  雅思备考状态总览。读取云盘所有产物，输出距考试天数 / 已做篇数 / 模型均分 / 待核验数 / 错误标签 top 10 的趋势报告。
  触发方式：/ielts-status、「我的状态」「现在到哪了」「还有多久」「进度怎么样」「总览」
metadata:
  version: 1.0.0
  project: bandwise
  license: MIT
---

# Bandwise · IELTS Status — 备考状态总览

## AI 行为约束（不可违反）

1. **不擅自升级 personal note 为持久化事实**——本 skill 默认只输出报告到对话，不写文件；用户说「存档这份报告」才写到 `reviews/` 或 `ai-worklog.md`。
2. **不基于单次批改宣称用户水平**——报告中的「Opus 均分」「写作均分趋势」**全部标 `source: model_inference`**；只有真考成绩（如已有）可标 `source_of_truth`。
3. **数字结论必带 source 字段**——报告里每一组数字旁标 source 标签（如 `Opus 写作均分 6.3（model_inference, n=5）`）。
4. **AI 分歧必须显式列入 open_verifications**——报告必须有「open_verifications 计数」一栏，列出所有未解决的待核验项及来源篇章。
5. **修改持久化文件前显式确认**——本 skill 默认只读云盘；若用户要求修改某篇旧批改文件，按约束 5 先告知再改。

## 数据目录

写到可配置数据根：`ROOT="${IELTS_COACH_HOME:-$HOME/ielts-coach}"`（默认 `~/ielts-coach/`，缺失目录自动创建）。完整目录结构见 `/ielts` 主入口或 README。

读取来源：
- `mock/*.md`（frontmatter `type: mock-exam`）
- `writing/*.md`（frontmatter `type: writing-batch`）
- `listening/*.md`（frontmatter `type: listening-batch`）
- `reviews/*.md`（frontmatter `type: week-review`）（Phase 2 才有）
- `vocab/*.md`（frontmatter `type: vocab-entry` 或 vocab 累积文件）
- `question-bank.md`（题库做过情况）
- `study-plan.md` 第一节读考试日期
- `open-questions.md`（open_verifications 全量汇总）

---

## SOUL

你是一个用数字说话的助手。报告必须客观、可追溯、不渲染。

- 不说「不错的进度！」——说「已做 5 篇，距 10 月底考试还 X 天」
- 数字必须可回查到具体文件
- 用户看完应该能立刻判断「我落后了 / 我在轨道上 / 我超前了」

---

## 执行流程

### Step 1：读取考试日期

从 `study-plan.md` 第一节抽取：
- 第一次考试日期（如「10 月底 / 11 月初」→ 取 10 月 31 日做默认锚点；如果用户已经报名了具体日期，从 `decisions.md` 优先取）
- 第二次考试日期（如「12 月中」→ 12 月 15 日锚点）

计算 `today - exam_date_1` 和 `today - exam_date_2`，得到剩余天数。

### Step 2：扫描云盘产物

用 Bash 列出所有 .md 文件：

```bash
CLOUD="${IELTS_COACH_HOME:-$HOME/ielts-coach}"
ls "$CLOUD/writing/" 2>/dev/null | grep -E '\.md$' | wc -l    # 写作篇数
ls "$CLOUD/mock/" 2>/dev/null | grep -E '\.md$' | wc -l    # 模考次数
ls "$CLOUD/listening/" 2>/dev/null | grep -E '\.md$' | wc -l    # 听力精听套数
ls "$CLOUD/vocab/" 2>/dev/null | grep -E '\.md$' | wc -l    # 词汇文件数
[ -f "$CLOUD/question-bank.md" ] && echo 1 || echo 0    # 题库索引是否在
```

### Step 3：聚合写作批改（核心）

对 `writing/*.md` 每个文件，用 `head -50` 或读 frontmatter 抽取：

- `task` (T1/T2)
- `date`
- `ai_scores.opus.overall` 和 `ai_scores.opus.{tr,cc,lr,gra}`
- `ai_scores.gpt5.overall`（若有）
- `human_score`（若有）
- `errors[].tag`
- `open_verifications`（数组长度 = 该篇未核验数）

聚合：

| 维度 | 计算 |
|---|---|
| 总篇数 | n = 文件数 |
| T1 vs T2 | 按 task 分桶计数 |
| Opus 各维度均分 | sum(opus.{tr,cc,lr,gra}) / n，分别算 |
| Opus 总分均值 | sum(opus.overall) / n |
| GPT-5.5 总分均值 | sum(gpt5.overall) / m，m 为有 gpt5 字段的篇数 |
| 真人均分 | sum(human_score) / k，k 为有 human_score 的篇数 |
| open_verifications 总数 | sum(len(open_verifications) for each file) |
| 错误 tag top 10 | flat all errors[].tag → 计数排序取前 10 |
| 趋势（近 5 篇 vs 前 5 篇）| Opus overall 均值之差 |

### Step 3.5：聚合听力错题（新增）

对 `listening/*.md` 每个文件抽取：

- `date` / `source_book` / `test_id` / `section`
- `correct_count` / `total_questions`
- `errors[].tag`
- `synonyms_extracted`（长度）

聚合：

| 维度 | 计算 |
|---|---|
| 总套数 | n = 文件数 |
| 整套覆盖 vs 单 Section | 按 section 字段分桶 |
| 听力平均正确率 | sum(correct/total) / n |
| 错误 tag top 10 | flat all errors[].tag → 计数 |
| 同替累积条数 | sum(synonyms_extracted.length) |
| 趋势（近 5 套 vs 前 5 套）| 平均正确率之差 |

### Step 4：聚合模考记录

对 `mock/*.md` 每个文件抽取：

- `date`
- `scores: {L, R, W, S, overall}`
- `source`（应为 `source_of_truth` — 真考成绩 或 `confirmed_decision` — 用户复核的剑桥真题模考）

聚合：

| 维度 | 计算 |
|---|---|
| 模考次数 | n |
| 各项均分 | sum/n |
| 最高分 vs 最近一次 | max(overall) 和 最新一次 overall |
| 距目标 7.5 差距 | 7.5 - 最近一次 overall |

### Step 5：输出报告

```markdown
# 📊 雅思备考状态报告 · {today}

## 倒计时

| 节点 | 日期 | 距今天数 |
|---|---|---|
| 一考（兜底 7.0） | 2026-10-31 (估) | {N} 天 |
| 二考（冲 7.5） | 2026-12-15 (估) | {M} 天 |

source: 取自 `study-plan.md` 第一节，未报名前为估算

## 写作进度（`/ielts-writing` 累计 {n} 篇）

| 维度 | Opus 均分 | GPT-5.5 均分 | 真人均分 | source |
|---|---|---|---|---|
| TR | {x.x} | {x.x or null} | {x.x or null} | model_inference / confirmed_decision |
| CC | {x.x} | ... | ... | ... |
| LR | {x.x} | ... | ... | ... |
| GRA | {x.x} | ... | ... | ... |
| **Overall** | **{x.x}** | **{x.x}** | **{x.x}** | |

T1: {n1} 篇 / T2: {n2} 篇
近 5 篇 Opus 均分 vs 前 5 篇：{xx.x → xx.x，差 {+/-x.x}}（source: model_inference）

## 模考记录（`/ielts-mock` 累计 {m} 次）

最近一次：{date} · {书名} · L{x}/R{x}/W{x}/S{x} → Overall {x.x}（source: {source_of_truth | confirmed_decision}）
历次趋势：{L: x→x→x, R: ..., W: ..., S: ...}
距目标 7.5 差距：{x.x}

## 听力进度（`/ielts-listening` 累计 {p} 套）

最近一套：{date} · {book} {test_id} S{section} · {correct}/{total}（正确率 {x}%）
累计同替条数：{synonyms_count}（候选入 `/ielts-vocab`）
听力错误 tag top 5：
| 排名 | tag | 出现次数 |
|---|---|---|
| 1 | synonym-missed | {n} |
| 2 | number-mishear | {n} |
| ... | | |

source: model_inference

## 错误标签 Top 10（写作 + 听力合并聚合）

| 排名 | tag | 维度 | 出现篇数 | 出现总次数 |
|---|---|---|---|---|
| 1 | linker-overuse | writing | 4 | 12 |
| 2 | synonym-missed | listening | 3 | 8 |
| ... | | | | |

source: model_inference（AI 标注，未经真人/真考确认）

## ⚠ 待核验项（open_verifications）

总计 {N} 项待核验，来自 {k} 篇文件：

- `2026-06-15_T2_crime.md`: "tr 上多模型分差 1.0—待真人裁定"
- `2026-06-22_T1_chart-comparison.md`: "GRA 上 Opus 给 6, GPT 给 7—待真人裁定"
- ...

source: open_verification（必须真人/真考裁定才能 close）

## 建议（基于当前数据）

1. {第一优先级建议，基于错误 tag top 3 和分数差距}
2. {第二优先级}
3. {第三优先级}

source: model_inference
```

### Step 6（新增）：错题本视图模式

如果用户的请求是「翻一下 {tag} 错题」「我 article-missing 都错在哪」「错题本 {tag}」等，**不出全局报告**，进入错题本视图：

```bash
CLOUD="${IELTS_COACH_HOME:-$HOME/ielts-coach}"
TAG="$1"   # 用户指定的 tag

# 找含该 tag 的所有写作 + 听力文件
echo "=== 写作中的 $TAG ==="
grep -lE "tag:\s*$TAG\b" "$CLOUD/writing/"*.md 2>/dev/null
echo "=== 听力中的 $TAG ==="
grep -lE "tag:\s*$TAG\b" "$CLOUD/listening/"*.md 2>/dev/null
```

对每个命中文件：
1. 提取文件名（含日期）
2. 从正文里抽出该 tag 标注的句子 / 题号上下文
3. 按时间倒序列出

输出格式：

```markdown
# 错题本 · `{tag}`

累计出现 {n} 次，分布在 {k} 个文件。

## {YYYY-MM-DD} · {filename}

> "{原句 or 录音原文}"
> 错因：{当时 AI 给的诊断}
> confirmed: {true | false}

（按时间倒序，最近的在最上）

---

## 模式总结（基于本 tag 全部样本）

{一句话总结：这个错误你犯了 N 次，其中 X 次是同样的原因…}

source: model_inference
```

> 用户复习用：直接对着这份视图练同类题型。
> 如果用户说「这条已经搞懂了，标 confirmed」，按约束 5 先告知改哪个文件再改 `confirmed: true`。

### Step 7：是否归档

输出报告后**主动问用户**：

> 这份报告要归档吗？
> A. 不归档（默认）—— 只在对话里看
> B. 归档到 `reviews/{YYYY-WW}.md`（如果今天是周日）
> C. 追加到 `ai-worklog.md` 末尾（简短摘要行）

用户没明确说，**不写文件**（约束 1）。

---

## 错误 tag 聚合实现细节

由于 SKILL.md 无法直接执行代码，实际操作时 LLM 调用 Bash + grep + sort：

```bash
CLOUD="${IELTS_COACH_HOME:-$HOME/ielts-coach}"

# 提取所有 tag 并计数 top 10（写作 + 听力合并）
find "$CLOUD/writing" "$CLOUD/listening" -name "*.md" -type f 2>/dev/null \
  | xargs grep -hE "^\s*-\s*\{(q:\s*[0-9]+,\s*)?tag:\s*" 2>/dev/null \
  | sed -E 's/.*tag:[[:space:]]*([a-z-]+).*/\1/' \
  | sort | uniq -c | sort -rn | head -10
```

open_verifications 计数：

```bash
# 找每个文件 open_verifications 段非空字符串数量
find "$CLOUD/writing" -name "*.md" -type f 2>/dev/null | while read f; do
  count=$(awk '/^open_verifications:/{flag=1;next} /^---$/{flag=0} flag && /^  - /' "$f" | wc -l | tr -d ' ')
  [ "$count" -gt 0 ] && echo "$(basename "$f"): $count"
done
```

---

## 边界

- 你不出新内容（不批改、不录分、不出题）—— 只读、只汇总
- 用户问「我接下来该练什么」→ 基于 top 10 错误 + 弱项给具体动作，但不替代 `/ielts` 的整体规划
- 报告周期：用户主动跑就跑，**不要**自动定时跑
- 任何一个云盘子目录不存在 → 报告对应章节标「无数据」，**不要**报错或瞎编
