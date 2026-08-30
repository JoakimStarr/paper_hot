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

# 默认五轮流式顺序（每方 2 轮）：pro_1 正方陈述 -> con_1 反方反驳 -> pro_2 正方再回应 -> con_2 反方再回应 -> judge 评审裁决
ROUND_SEQUENCE: List[str] = ["pro_1", "con_1", "pro_2", "con_2", "judge"]

ROLE_LABELS: Dict[str, Tuple[str, str]] = {
    "pro_1": ("正方陈述", "pro"),
    "con_1": ("反方反驳", "con"),
    "pro_2": ("正方再回应", "pro"),
    "con_2": ("反方再回应", "con"),
    "judge": ("评审裁决", "judge"),
}

_MAX_ROUNDS_PER_SIDE = 3


def build_round_sequence(rounds_per_side: int = 2) -> List[str]:
    """按每方轮数自适应生成轮序：pro_i/con_i 交替 N 轮 + judge。

    rounds_per_side 钳制到 [1, 3]；与默认常量 ROUND_SEQUENCE（N=2）保持一致输出。
    """
    n = max(1, min(int(rounds_per_side if rounds_per_side is not None else 2), _MAX_ROUNDS_PER_SIDE))
    rounds: List[str] = []
    for i in range(1, n + 1):
        rounds.append(f"pro_{i}")
        rounds.append(f"con_{i}")
    rounds.append("judge")
    return rounds


def round_label(round_name: str) -> Tuple[str, str]:
    """任意轮名的展示标签与立场（多轮自适应版 ROLE_LABELS）。"""
    if round_name == "judge":
        return "评审裁决", "judge"
    side, idx = round_name.rsplit("_", 1)
    i = int(idx)
    if side == "pro":
        return ("正方陈述" if i == 1 else f"正方第{i}轮", "pro")
    return ("反方反驳" if i == 1 else f"反方第{i}轮", "con")


def build_messages(
    topic: str,
    papers: List[dict],
    stats: dict,
    competition: dict,
    history: List[Tuple[str, str]],
    round_name: str,
    rounds_per_side: int = 2,
) -> List[dict]:
    """构造某一轮的 prompt：角色人格 + Script 证据 + 历史轮次 + 本轮指令。

    history：[(轮次标签, 该轮正文), ...]，不含当前轮。
    rounds_per_side：每方轮数，用于区分"中间轮回应"与"末轮最后辩护"的措辞。
    """
    papers_text = validate_skill.build_papers_text(papers, limit=30)
    script_evidence = validate_skill.build_script_evidence(stats, competition)
    label, side = round_label(round_name)
    history_text = _format_history(history)
    role_instruction = _role_instruction(side, label, round_name, rounds_per_side)
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


def _role_instruction(side: str, label: str, round_name: str, rounds_per_side: int = 2) -> str:
    """各角色的本轮任务指令（按 (i, N) 区分中间轮回应与末轮最后辩护）。"""
    common = f"本轮的发言将呈现为「{label}」。"
    try:
        i = int(round_name.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        i = 1
    n = max(1, min(int(rounds_per_side if rounds_per_side is not None else 2), _MAX_ROUNDS_PER_SIDE))
    is_last = i >= n
    if side == "pro":
        if i == 1:
            return (
                common + "你持**支持**立场：论证该选题的研究价值与可行性。"
                "说明它解决什么问题、为何值得做（引用热度/趋势/关键词证据）、"
                "现有研究留下了什么空位（引用相似度最高的几篇 [n] 说明差异）。"
            )
        if is_last:
            return (
                common + "你持**支持**立场，本轮是回应反方质疑后的最后辩护："
                "逐条回应反方提出的拥挤/可行性质疑（引用证据说明为何低估），"
                "并补充一个反方未考虑的差异化切入点。"
            )
        return (
            common + "你持**支持**立场，本轮继续回应反方上一轮的质疑："
            "逐条反驳其关于拥挤度/可行性/数据可得性的论点（引用证据），"
            "并指出反方忽略或低估的证据。"
        )
    if i == 1:
        return (
            common + "你持**反对/质疑**立场：客观评估该选题的风险与拥挤度。"
            "指出它与最相似文献的实质重合（引用 [n]）、方向竞争状况（引用 Script 统计）、"
            "数据与方法可行性的隐患。证据不足的部分如实说明，不要为了反对而反对。"
        )
    if is_last:
        return (
            common + "你持**反对/质疑**立场，本轮是最后的再质疑："
            "对正方新提出的差异化切入点评其现实障碍（数据可得性/方法成熟度/样本量），"
            "并评估正方是否回避了最关键的竞争证据。"
        )
    return (
        common + "你持**反对/质疑**立场，本轮继续质疑正方："
        "对正方上轮的辩护逐条检视其证据强度，指出仍未被回答的关键问题。"
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


def build_followup_messages(
    topic: str,
    papers: List[dict],
    stats: dict,
    competition: dict,
    history: List[dict],
    role: str,
    prompt: str,
) -> List[dict]:
    """继续追问（辩论已结束后追加单轮）：历史轮次 + 角色指令 + 用户问题。

    history：已完成的轮次 [{id,label,model,text}]（也可传 [(label,text)]）。
    role：pro | con | judge | assistant。
    """
    papers_text = validate_skill.build_papers_text(papers, limit=30)
    script_evidence = validate_skill.build_script_evidence(stats, competition)
    role_instruction = {
        "pro": "你继续以**正方**立场回应（可先反驳反方上轮观点，再补充论证）：",
        "con": "你继续以**反方**立场回应（可继续质疑正方上轮论证，或提出新的风险点）：",
        "judge": "你继续以**评审**身份回应（可点评双方论点、补充裁决意见）：",
        "assistant": "你作为中立专家，结合已有辩论回应：",
    }.get(role, "你继续回应：")
    history_blocks = []
    for h in history:
        if not isinstance(h, dict):
            continue
        label = h.get("label") or h.get("id") or ""
        text = (h.get("text") or "").strip()
        if len(text) > 1200:
            text = text[:1200] + "…（该轮过长已截断）"
        history_blocks.append(f"【{label}】\n{text}")
    history_text = "\n\n".join(history_blocks)

    system_prompt = f"""你是一位学术选题辩论专家，正在继续一场关于以下选题的辩论。

候选选题：{topic}

【Script 证据——系统预计算的确定性统计，非你的判断；引用时必须原样复述，标注为系统统计】
{script_evidence}

【召回论文列表（按相似度降序；[n] 编号即引用编号，仅限 [1]-[{len(papers[:30])}]）】
{papers_text}

【已进行的辩论轮次】
{history_text or "（无）"}

{role_instruction}

【写作纪律】
- 回应要落到具体证据：关键判断先给量化依据（Script 数字或 [n] 编号）再展开；
- Script 数字原样引用，禁止改写/夸大/张冠李戴；[n] 只引用上方列表内的论文，严禁编造；
- 证据不足时如实说明并降低置信度；
- 用中文作答，markdown 格式，300-700 字。"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]


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
