<p align="center"><img src="assets/logo.svg" alt="Bandwise" width="116"></p>

# Bandwise · 雅思学习教练

在 Codex / Claude Code 中使用的中文雅思学习 Skill。一个入口接续已有计划，按需调用听说读写、词汇、模考、题库和进度模块。

训练流程为“先作答 → 反馈 → 用户修订或重答 → 下次复练”。10个Skill共用学习记录；GPT语音负责实际口语对话，Bandwise负责练前准备与练后接续。

本文对应当前 `main` 分支。已打标签的历史版本与当前功能可能不同；各Skill的 `metadata.version` 是模块版本，不等于新的GitHub Release。版本变化见 [CHANGELOG](CHANGELOG.md)。

## 日常怎么用

- “今天练雅思，还是一个单元单词加听力。”
- “查一下墨墨今天的进度。”
- “雅思王第3章第2节，50词错了8个，帮我记录。”
- “这篇作文先指出最影响得分的两个问题，我改完再看。”
- “按Part 2问我，等我答完再反馈。”
- “看看这周哪些错误复练后还存在。”

### 和GPT语音配合

说“准备一份GPT语音口语练习包”，助手会给可直接粘贴的题目、模式与导出要求。你在ChatGPT里实际对话，结束时让它生成文字记录，再把结果交回来说“保存这次口语练习”。本地脚本会保留原回答、四维AI反馈与复练任务；同一结果不重复计数、更正不覆盖原件。下次说“接着上次口语练”即可。

这条路线需要把练后结果交回来，尚无自动读取ChatGPT会话的连接。保存脚本不调用模型、不消耗API额度，也不自行听音频或产生新评分。完整用法见[语音交接流程](ielts-speaking/references/voice-workflow.md)。

公开口语题库入口见[2026年9月来源核查](ielts-question-bank/references/speaking-sources-2026-09.md)：有可读的保留题预览和预测题，尚未核实完整当季终版。用户的等待更新安排不会因此自动解除。

已有计划直接接续；四科都有能力，不要求每天四科全练。仅询问影响当次练习的缺项，普通查询不生成新文件。

## 能力与边界

| 模块 | 用途 |
|---|---|
| `ielts` | 统一入口、读取当前安排、按需分流 |
| `ielts-listening` | 整套/单Part、精听、雅思王结果导入与错因复练 |
| `ielts-reading` | 原文定位、T/F/NG、标题匹配与同义替换 |
| `ielts-writing` | Academic/GT Task 1/2反馈、用户修订与迁移复测 |
| `ielts-speaking` | Part 1/2/3陪练、GPT语音练习包、四维反馈保存与复练 |
| `ielts-vocab` | 教材单元、墨墨进度、错词候选与语境抽测 |
| `ielts-mock` | 原始答对数/分数录入、缺科处理、Overall计算 |
| `ielts-question-bank` | 材料目录、已做范围与第三方口语题库版本 |
| `ielts-plan` | 已有日程接续与适量调整 |
| `ielts-status` | 来源、材料范围、首次/复练分组汇总 |

- 墨墨：先用当前已提供的真实MCP工具；没有时可配置已有官方API脚本。Skill不把API脚本伪装成MCP，也不内置Token。新增词和提前复习分别遵守用户授权。
- 雅思王：支持合法导出、结果页、截图或口述。尚未核验到开放的个人进度API，不能宣称已自动同步；不包含受限题库或配套音频。
- 音频：依据当前模型/工具的实际能力处理。只能读转写时不评价发音，不把文本练习计成听力练习。
- 评分：以[官方评分说明](https://ielts.org/take-a-test/your-results/ielts-scoring-in-detail)为依据。单Part/听写不换算Band；AI估分、教师反馈和正式成绩分开。无“固定提分周期”“固定减0.5”或“万能故事命中率”保证。

## 安装

### 前提

- 使用能够读取本地Skill和文件的Codex或Claude Code。
- 本地保存、验证和图表脚本使用Python标准库；建议Python 3.12或更新版本，CI使用3.12验证。
- GPT语音练习使用你自己的ChatGPT会话。墨墨连接为可选能力，需已有可用MCP或官方API连接器；本仓库不附带 `maimemo_sync.py`、账号或Token。

### 首次安装

先克隆仓库，再从仓库根目录执行下面的安装块。10个目录通过相对链接共享规则，需要一并安装。命令会在发现任何已有目标时停止，避免混装或覆盖本地版本。

```sh
git clone https://github.com/lilialla/bandwise.git
cd bandwise
```

```sh
bash <<'SH'
set -eu
# Claude Code用户将下一行改为 "$HOME/.claude/skills"
skill_dest="$HOME/.codex/skills"
for skill in ielts ielts-*; do
  test -f "$skill/SKILL.md"
  if [ -e "$skill_dest/$skill" ] || [ -L "$skill_dest/$skill" ]; then
    printf '已有安装，请先核对版本：%s\n' "$skill_dest/$skill" >&2
    exit 1
  fi
done
mkdir -p "$skill_dest"
for skill in ielts ielts-*; do
  cp -R "$skill" "$skill_dest/"
done
SH
```

在你自己的本地checkout上，也可以把这10个目录分别链接到运行器的技能目录。保持它们为兄弟目录，不把个人数据放入技能目录。开始一个新任务以刷新技能列表；也可以明确让助手读取本地 `ielts/SKILL.md`。

当前对话里说“今天练雅思”即可；运行器支持显式调用时也可用 `$ielts` / `/ielts`。

### 已有安装如何更新

先核对仓库工作区和安装目录，保留自己的修改。仓库干净时可用 `git pull --ff-only` 获取更新；遇到分叉或冲突先处理，不强制重置。

- 符号链接安装：确认链接指向更新后的checkout，新任务即可读取该版本。
- 复制安装：更新checkout不会自动更新副本。对比并备份旧安装后，再整体更新10个目录；不要把首次安装块改成强制覆盖命令。

升级不迁移、重写或删除学习记录，也不自动更改本机配置。

## 本机设置和学习记录

公共仓库只存通用规则，个人记录存于现有学习目录。Skill按以下优先级解析数据根：

1. 环境变量 `IELTS_COACH_HOME`；
2. 可选的 `~/.config/bandwise/config.json` 中 `data_root`；
3. 未配置时默认 `~/ielts-coach`。

配置字段均为可选，不含凭证：

| 字段 | 用途 |
|---|---|
| `data_root` | 已有私人学习数据目录 |
| `plan_path` | 已有权威计划文件；无此字段才读数据根的 `study-plan.md` |
| `timezone` | 业务日期所用时区 |
| `routine` | 用户确认的当前节奏，未确认项保持未知 |
| `maimemo.script`、`maimemo.python` | 已有连接器和解释器的本机路径 |

配置中的 `routine` 可保存 `daily_vocabulary_units`、`vocabulary_book`、`current_unit`、`listening`、`speaking` 等当前安排。用户新指令优先；不从示例数值推断其真实目标。

`data_root`、`plan_path`、`maimemo.script`和`maimemo.python`建议填写展开后的完整本机路径，配置保存在仓库以外。没有已有计划或墨墨连接时省略相应字段；它们不是开始普通教学的前置条件。

连接器契约见[墨墨接入说明](ielts-vocab/references/maimemo.md)。现有 `maimemo_sync.py` 兼容路线需要 `status --json`、`add`、`advance` 等已核对命令；未配置时普通教学仍可用。

记录按需要存入 `writing/`、`listening/`、`reading/`、`speaking/`、`mock/`、`vocab/`。雅思王听写在 `listening/corpus/`。已有计划和工作区复盘路由优先，不再建立平行计划。查询默认不写；“记录这次练习”或既有自动记录授权才保存，初稿与修订、首次与复做保留关系。

GPT语音回传使用 `speaking/records/*.json`：每个文件同时保存原导出、哈希、导入时间和归一化评分。`record_id`标识导出版本，`session_id`标识一次实际练习；补转写或改分产生新版本，不增加场次。练习包尚无实际回答，不进入成绩目录。

私人目录700、文件600；Token仍留在原连接器凭证存储。归档留在本地，但提交给云模型的作文/录音会由对应模型服务处理；不宣称整个学习过程离线。

### 本地口语记录命令（可选）

日常只需把GPT返回的记录交给助手。自行调用脚本时，在仓库根目录运行下列命令；将导出文件路径换为真实路径。

```sh
# 查看参数与格式要求
python3 ielts-speaking/scripts/speaking_record.py --help
# 只预览，不写入学习目录
python3 ielts-speaking/scripts/speaking_record.py import ./speaking-export.json
# 已决定保存本次记录时执行
python3 ielts-speaking/scripts/speaking_record.py import ./speaking-export.json --save
# 只读统计场次、有效评分与下一次任务
python3 ielts-speaking/scripts/speaking_record.py status
```

如需指定数据根，`--root`必须放在 `import` 或 `status` 前。它优先于环境变量和私人配置。原始JSON上限2MB，已保存记录上限8MB；目录冲突、符号链接路径和同ID不同内容都会明确报错。格式和评分条件见[语音交接流程](ielts-speaking/references/voice-workflow.md)。

## 进度与兼容

已有档案不自动迁移。新记录继续保留可用的旧字段，增加作答ID、尝试类型、来源和核验状态。`ielts-status`按实际模型名、练习范围和初稿/修订分组。

仓库保留的 `scripts/dashboard.py` 是旧版可选图表：没有适配所有新字段、口语/墨墨/语料库，且部分目标与模型名固定。它不能作为新版完整进度或能力判断依据。新版日常直接在对话中使用 `ielts-status`，无需运行仪表盘。

## 验证与维护

```sh
python3 scripts/validate_skills.py
python3 -B -m unittest discover -s tests -v
```

第一条验证Skill结构与公共文件信息；第二条使用临时合成数据检查口语保存、分数依据、去重、更正和路径边界。CI还会编译根目录脚本。通过这些检查不代表真实语音评分已校准或保证提分；仍需用实际练习检验陪练效果。操作真实平台前使用只读查询或预览验证。

详细规范见 [CONTRIBUTING.md](CONTRIBUTING.md)，共用规则见 [practice-contract.md](ielts/references/practice-contract.md)。

## License

源码可见，采用 [PolyForm Noncommercial 1.0.0](LICENSE)，不是OSI开源许可。个人及许可涵盖的非商业使用免费；商业用途需要单独授权。联系：`1733970552@qq.com`、[buyunfadian.com](https://buyunfadian.com)或本仓库issue。没有自动发布或自动更新个人安装。
