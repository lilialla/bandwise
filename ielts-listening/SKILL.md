---
name: ielts-listening
description: |
  雅思听力训练与错题复盘。支持整套、单Part、精听和雅思王语料库结果导入，区分首次作答、复听与词汇听写。
metadata:
  version: 1.2.0
  project: bandwise
  license: PolyForm-Noncommercial-1.0.0
---

# Bandwise · 听力训练

先读 [共用约定](../ielts/references/practice-contract.md)；涉及分数读 [评分依据](../ielts/references/scoring.md)。雅思王/语料库/小程序结果再读 [雅思王接入](references/yasiwang.md)。

## 先识别材料和范围

- 整套或Part：书名版本、Test/Part、题目、用户答案、标准答案及可用音频/转写。
- 精听：用户可播放的音频片段；存在原文时先隐藏，练完再校对。
- 语料库：按专门参考文件导入章节、遍数、倍速、词数与错词。
- 只有书号没有题目时不能凭记忆补“官方原文”；先用已有合法材料或官方样题。

确认当前环境能否读取音频。能听时依据实际音频与时间码；不能听时用用户提供的转写分析内容，并说明无法独立核实声音。不能把展示数字列表当播放音频。

## 作答与复盘

1. 首次限时练习让用户先完整作答，不中途提示；训练模式按用户时间选择一个Part或短片段。
2. 核对题目要求、答案与拼写，报告 `correct_count / total_questions`。答案有争议时回到来源，缺答案不作确定扣分。
3. 每道需解释的错题给出：题号、原答案、标准答案与来源、原音/原文位置、关键差别、下一次识别办法。
4. 错因可用 `unknown-word`、`sound-word-mismatch`、`spelling-error`、`plural-ending`、`number-mishear`、`synonym-missed`、`distraction`、`instruction-misread`。用户确认走神才能记录 `attention-drift`；不能仅凭一题错认定口音问题。
5. 选一至三个主要问题复练：重听定位句 → 看原文解释 → 遮住原文再听/复述。遇到词汇问题，给少量候选交给词汇模块；账户写入遵守单独授权。

听力题型按真实题面处理：选择、匹配、地图/平面图标注、表格/笔记/流程/摘要填空、句子完成或简答。不要把阅读T/F/NG套入听力。

## 结果记录

沿用 `IELTS_COACH_HOME` 解析后的数据根；有保存授权时一场作答一个档案，整套不拆成四次模考。兼容字段如下，示例为虚构的单Part记录：

```yaml
---
type: listening-batch
record_id: example-part4-first
date: 2026-09-07
source_book: practice-sample
test_id: sample-1
section: 4
attempt_kind: first
timed: true
answer_seen_before: false
total_questions: 10
correct_count: 7
source_type: user_report
verification_status: unverified
source_ref: null
band_estimate: null
band_source: null
errors: []
synonyms_extracted: []
open_verifications: []
---
```

仅单Part成绩时 `band_estimate`、`band_source` 都为null；不能按正确率乘四、不能断言“S4七题就是7分”。没有错词明细时不编 `errors`；错因诊断保留AI判断来源。正文保存必要题目定位、复练结果和下一步即可。
