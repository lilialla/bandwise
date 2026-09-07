---
name: ielts-mock
description: |
  记录雅思模考或正式成绩，区分原始答对数、AI估分、教师反馈和成绩单，允许缺科并正确计算Overall。
metadata:
  version: 1.2.0
  project: bandwise
  license: PolyForm-Noncommercial-1.0.0
---

# Bandwise · 模考与成绩

先读 [共用约定](../ielts/references/practice-contract.md) 和 [评分依据](../ielts/references/scoring.md)。按用户明确记录指令保存到 `IELTS_COACH_HOME` 解析后的 `mock/`。

## 录入

1. 从现有对话提取日期、考试类型、试卷版本、首次/复做和各科来源。只有歧义影响记录时才问；用户只给L/R时直接记部分成绩，W/S留null。
2. 区分原始数和Band，例如“L35 R32”通常是正确题数，但缺试卷范围时先确认，不存成35分。
3. 只有完整40题且有可用换算依据才生成近似Band。不能依据一Part、听写或不明确范围生成整科分数。
4. 正式成绩单已查看并核对才标官方来源；用户口述真考仍是自述。已知为AI估分的W/S不能因用户确认数字而升级。
5. 四科同次且分数有效才计算Overall；缺科就null，不从上周补齐。实际正式Overall照录；算术冲突先核对成绩单，不能直接改原件。

保留 `type: mock-exam`、`date`、`scores`、`sources`、`raw_correct`、`open_verifications`，并加共用作答、核验与来源字段。Band支持0—9的整分/半分，原始分支持0—40整数。不同来源放在 `sources` 及 `score_evidence` 对应科目下。

以下为计算演示，不能导入成真实学习记录：

```yaml
scores:
  L: 7.5
  R: 7.5
  W: 6.0
  S: 6.0
  overall: 7.0
sources:
  L: model_inference
  R: model_inference
  W: model_inference
  S: model_inference
  overall: model_inference
```

该例平均6.75，Overall为7.0，不把未四舍五入均值写入overall。四科中有自估/AI估计时，Overall必须说明只是该组合的计算结果。

## 更正与查询

同场记录更正保留旧数字和依据，按记录ID修订，不重复增加模考次数。原始作答、答案已核对的正确数与Band推算分别保留。日常仅报告已记录的分项及来源；用户要求趋势时交给状态模块。
