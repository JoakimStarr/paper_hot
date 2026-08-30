"""选题评估辩论技能：正方/反方各两轮论证（全流式）-> 评审按预承诺 RUBRIC 裁决。

设计要点（延续 validate 技能的三条强化）：
1. 证据底座统一由后端确定性计算（build_script_evidence / build_papers_text），
   双方论证必须以 Script 证据与 [n] 召回论文为据，禁止编造库内论文；
2. 评审裁决复用 validate 的预承诺 RUBRIC（novelty/crowding/feasibility/gate，
   档位口径一致），输出以 ```json 头开始，后端 split_json_head 解析后走
   normalize_scores/apply_scores 落库——不产生第二套评分口径；
3. 每轮独立 system prompt（角色人格 + 证据 + 本轮指令），历史轮次以
   【正方陈述】…文本块注入下一轮，保证交锋连贯而非各说各话。
"""
from typing import Any, Dict, List, Tuple

from app.skills import validate as validate_skill

NAME = "debate"
DESCRIPTION = "选题评估辩论：正方/反方各两轮交锋 + 评审按预承诺标准裁决（novelty/crowding/feasibility/gate）"

# 五轮流式顺序：pro_1 正方陈述 -> con_1 反方反驳 -> pro_2 正方再回应 -> con_2 反方再回应 -> judge 评审裁决
ROUND_SEQUENCE: List[str] = ["pro_1", "con_1", "pro_2", "con_2", "judge"]

ROLE_LABELS: Dict[str, Tuple[str, str]] = {
    "pro_1": ("正方陈述", "pro"),
    "con_1": ("反方反驳", "con"),
    "pro_2": ("正方再回应", "pro"),
    "con_2": ("反方再回应", "con"),
    "judge": ("评审裁决", "judge"),
}


def build_messages(
    topic: str,
    papers: List[dict],
    stats: dict,
    competition: dict,
    history: List[Tuple[str, str]],
    round_name: str,
) -> List[dict]:
    """构造某一轮的 prompt：角色人格 + Script 证据 + 历史轮次 + 本轮指令。

    history：[(轮次标签, 该轮正文), ...]，不含当前轮。
    """
    papers_text = validate_skill.build_papers_text(papers, limit=30)
    script_evidence = validate_skill.build_script_evidence(stats, competition)
    label, side = ROLE_LABELS.get(round_name, (round_name, "pro"))
    history_text = _format_history(history)
    role_instruction = _role_instruction(side, label, round_name)
    # 评审轮额外追加裁决契约（JSON 头 + 正文小节固定顺序）
    if round_name == "judge":
        role_instruction += "\n\n" + judge_head_schema()

    system_prompt = f"""你是一位学术选题辩论专家，正在参与对候选选题的评估辩论。

候选选题：{topic}

【Script 证据——系统预计算的确定性统计，非你的判断；引用时必须原样复述，标注为系统统计】
{script_evidence}

【召回论文列表（按相似度降序；[n] 编号即引用编号，仅限 [1]-[{len(papers[:30])}]）】
{papers_text}
{role_instruction}

【写作纪律】
- 论证必须落到具体证据：每个关键判断先给量化依据（Script 数字或 [n] 编号）再展开；
- Script 证据中的数字原样引用，禁止改写/夸大/张冠李戴；[n] 只引用上方列表内的论文，严禁编造；
- 证据不足时如实说明并降低置信度，禁止强行论证（正方禁硬吹、反方禁强黑）；
- 用中文作答，markdown 格式，500-900 字。
{_history_block(history_text)}"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请完成第「{label}」这一轮。"},
    ]


def _role_instruction(side: str, label: str, round_name: str) -> str:
    """各角色的本轮任务指令。"""
    common = f"本轮的发言将呈现为「{label}」。"
    if side == "pro":
        if round_name == "pro_1":
            return (
                common + "你持**支持**立场：论证该选题的研究价值与可行性。"
                "说明它解决什么问题、为何值得做（引用热度/趋势/关键词证据）、"
                "现有研究留下了什么空位（引用相似度最高的几篇 [n] 说明差异）。"
            )
        return (
            common + "你持**支持**立场，本轮是回应反方质疑后的最后辩护："
            "逐条回应反方提出的拥挤/可行性质疑（引用证据说明为何低估），"
            "并补充一个反方未考虑的差异化切入点。"
        )
    if round_name == "con_1":
        return (
            common + "你持**反对/质疑**立场：客观评估该选题的风险与拥挤度。"
            "指出它与最相似文献的实质重合（引用 [n]）、方向竞争状况（引用 Script 统计）、"
            "数据与方法可行性的隐患。证据不足的部分如实说明，不要为了反对而反对。"
        )
    return (
        common + "你持**反对/质疑**立场，本轮是回应正方辩护后的再质疑："
        "对正方新提出的差异化切入点评其现实障碍（数据可得性/方法成熟度/样本量），"
        "并评估正方是否回避了最关键的竞争证据。"
    )


def _history_block(history_text: str) -> str:
    if not history_text:
        return ""
    return f"""

【已进行的辩论轮次（引用时保持一致口径，不要重复已说过的内容）】
{history_text}"""


def _format_history(history: List[Tuple[str, str]]) -> str:
    """历史轮次 -> 文本块（供下一轮注入上下文）。"""
    blocks = []
    for label, text in history:
        t = (text or "").strip()
        if len(t) > 1200:
            t = t[:1200] + "…（该轮过长已截断）"
        blocks.append(f"【{label}】\n{t}")
    return "\n\n".join(blocks)


def judge_head_schema() -> str:
    """评审 JSON 头的输出契约说明（与 validate.RUBRIC 口径一致）。"""
    return """【裁决输出契约——严格遵守】
第一行输出 ```json 代码块（之后才是正文）：
{
  "novelty": 1-10 的整数,
  "crowding": "低|中|高",
  "feasibility": 1-10 的整数,
  "gate": "pass|caution|avoid"
}
正文用 markdown，依次包含：
## 双方论点回顾
各用一句概括正方最有说服力的论点与反方最有分量的质疑（引用对应 [n] / Script 数字）。
## 裁决依据
对照预承诺档位逐项说明为何落在该档（novelty 按 max_similarity、crowding 按 recent_1y_count 与平均相似度、feasibility 按数据可得性）。
## 评审条件
以 if-then 形式给出采纳该选题的前提条件（2-3 条，每条明确：满足什么条件就做 / 什么情况放弃）。
## 结论
gate 判定 + 一句可执行建议。"""
