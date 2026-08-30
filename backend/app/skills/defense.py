"""选题答辩技能：候选人自述研究设计 -> 评委逐轮质询 -> 候选人应答 -> 合议裁定（全流式）。

与辩论（skills/debate.py）互补：辩论是正反交锋找分歧，答辩是"质询-应答"检验研究设计
的完备性。设计要点沿用 debate/validate 的三条强化：
1. 证据底座由后端确定性计算（build_script_evidence / build_papers_text），
   质询与应答必须引用 Script 统计与 [n] 召回论文，禁止编造；
2. 合议裁定复用 validate 的预承诺 RUBRIC（novelty/crowding/feasibility/gate）+
   新增结论字段 verdict（通过|修改后通过|不通过），JSON 头由后端 split_json_head 解析
   走 apply_scores 落库——与验证/辩论同一评分口径；
3. 每轮独立 system prompt，历史轮次以【评委质询】…文本块注入下一轮，保持质询连贯。
"""
from typing import Dict, List, Tuple

from app.skills import validate as validate_skill

NAME = "defense"
DESCRIPTION = "选题答辩：候选人自述 + 评委逐轮质询 + 候选人应答 + 合议裁定（novelty/crowding/feasibility/gate + verdict）"

_MAX_ROUNDS_PER_SIDE = 3

# 质询维度轮换表（按质询序号循环取用）
_EXAMINER_DIMENSIONS = [
    "新颖性：与最相似文献的实质差异在哪里（引用 [n]，说明它的因变量/机制/方法与本选题的差别）",
    "识别策略与方法：如何解决反向因果/遗漏变量/自选择等内生性问题；方法是否成熟、有无更干净的设计",
    "数据可得性与样本量：依赖的数据是否公开可得（CSMAR/Wind/CFPS 等）、样本量与覆盖范围是否支撑结论",
    "竞争与拥挤度：该方向近一年竞争状况（引用 recent_1y_count / top_authors），差异化空间是否真实存在",
]


def build_round_sequence(rounds_per_side: int = 2) -> List[str]:
    """自适应轮序：candidate_0 自述 -> examiner_k/candidate_k 交替 N 轮 -> panel 合议。

    rounds_per_side 钳制到 [1, 3]。
    """
    n = max(1, min(int(rounds_per_side if rounds_per_side is not None else 2), _MAX_ROUNDS_PER_SIDE))
    rounds: List[str] = ["candidate_0"]
    for i in range(1, n + 1):
        rounds.append(f"examiner_{i}")
        rounds.append(f"candidate_{i}")
    rounds.append("panel")
    return rounds


def round_label(round_name: str) -> Tuple[str, str]:
    """任意轮名的展示标签与角色（candidate/examiner/panel）。"""
    if round_name == "panel":
        return "合议裁定", "panel"
    side, idx = round_name.rsplit("_", 1)
    if side == "candidate":
        return ("候选人自述" if idx == "0" else f"候选人应答·第{idx}轮", "candidate")
    return (f"评委质询·第{idx}问", "examiner")


def build_messages(
    topic: str,
    papers: List[dict],
    stats: dict,
    competition: dict,
    history: List[Tuple[str, str]],
    round_name: str,
    rounds_per_side: int = 2,
) -> List[dict]:
    """构造某一轮的 prompt：角色人格 + Script 证据 + 历史轮次 + 本轮指令。"""
    papers_text = validate_skill.build_papers_text(papers, limit=30)
    script_evidence = validate_skill.build_script_evidence(stats, competition)
    label, role = round_label(round_name)
    history_text = _format_history(history)
    role_instruction = _role_instruction(role, label, round_name, rounds_per_side)
    if round_name == "panel":
        role_instruction += "\n\n" + panel_verdict_schema()

    system_prompt = f"""你是一位学术论文答辩参与者，正在对候选选题进行答辩质询与合议。

候选选题：{topic}

【Script 证据——系统预计算的确定性统计，非你的判断；引用时必须原样复述，标注为系统统计】
{script_evidence}

【召回论文列表（按相似度降序；[n] 编号即引用编号，仅限 [1]-[{len(papers[:30])}]）】
{papers_text}
{role_instruction}

【写作纪律】
- 论证必须落到具体证据：每个关键判断先给量化依据（Script 数字或 [n] 编号）再展开；
- Script 证据中的数字原样引用，禁止改写/夸大/张冠李戴；[n] 只引用上方列表内的论文，严禁编造；
- 证据不足时如实说明并降低置信度，禁止硬撑（候选人不得回避硬伤、评委不得无据苛责）；
- 用中文作答，markdown 格式，400-800 字（评委质询可更短，聚焦 1-2 个尖锐问题）。
{_history_block(history_text)}"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请完成第「{label}」这一环节。"},
    ]


def _role_instruction(role: str, label: str, round_name: str, rounds_per_side: int = 2) -> str:
    """各角色的本轮任务指令。"""
    common = f"本环节的发言将呈现为「{label}」。"
    n = max(1, min(int(rounds_per_side if rounds_per_side is not None else 2), _MAX_ROUNDS_PER_SIDE))
    if role == "candidate":
        if round_name == "candidate_0":
            return (
                common + "你是**候选人**，向答辩委员会陈述你的研究设计："
                "1) 研究问题与假说（它解决什么问题、为何重要）；"
                "2) 方法与识别策略（引用文献中的惯例并说明你的设计）；"
                "3) 数据来源与样本；4) 创新点（与最相似的 1-2 篇 [n] 的差异）。"
                "陈述要具体、可检验，引用证据支撑每一步。"
            )
        if round_name == f"candidate_{n}":
            return (
                common + "你是**候选人**，本轮为最终陈词：逐条回应评委提出的问题（引用证据），"
                "坦诚说明无法完全解决的部分并给出补救思路，最后总结为什么该选题值得做。"
            )
        return (
            common + "你是**候选人**，回应评委上一轮的质询："
            "逐条给出有证据支撑的答复；无法完全回答的部分如实承认并说明如何补救，不要回避。"
        )
    if role == "examiner":
        try:
            k = int(round_name.rsplit("_", 1)[1])
        except (ValueError, IndexError):
            k = 1
        dim = _EXAMINER_DIMENSIONS[(k - 1) % len(_EXAMINER_DIMENSIONS)]
        return (
            common + f"你是**答辩评委**，本轮质询聚焦：{dim}。"
            "提出 1-2 个尖锐但具体的问题（可引用 Script 统计或 [n] 论文作为质询依据），"
            "不要泛泛而谈，问题要指向候选人必须给出证据的地方。"
        )
    # panel
    return (
        common + "你是**答辩委员会主席**，主持合议：综合候选人陈述与全部质询应答，"
        "对照预承诺评分标准给出裁定，并给出可执行的修改意见。"
    )


def panel_verdict_schema() -> str:
    """合议裁定 JSON 头输出契约（validate 4 轴 + verdict 结论）。"""
    return f"""【裁定输出契约——严格遵守】
第一行输出 ```json 代码块（之后才是正文）：
{{
  "novelty": 1-10 的整数,
  "crowding": "低|中|高",
  "feasibility": 1-10 的整数,
  "gate": "pass|caution|avoid",
  "verdict": "通过|修改后通过|不通过"
}}
正文用 markdown，依次包含：
## 质询焦点回顾
各用一句概括评委最有分量的质询与候选人最具说服力的应答（引用对应 [n] / Script 数字）。
## 裁定依据
对照预承诺档位逐项说明为何落在该档（novelty 按 max_similarity、crowding 按 recent_1y_count 与平均相似度、feasibility 按数据可得性）。
## 修改意见
2-3 条具体可执行的修改意见（每条明确：改什么、怎么改、为什么）。
## 结论
verdict 判定 + 一句可执行建议。"""


def _history_block(history_text: str) -> str:
    if not history_text:
        return ""
    return f"""

【已进行的答辩环节（保持口径一致，不要重复已说过的内容）】
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
    """继续追问（答辩已结束后追加单轮）：历史轮次 + 角色指令 + 用户问题。

    history：已完成的轮次 [{id,label,model,text}]。
    role：candidate | examiner | panel | assistant。
    """
    papers_text = validate_skill.build_papers_text(papers, limit=30)
    script_evidence = validate_skill.build_script_evidence(stats, competition)
    role_instruction = {
        "candidate": "你继续以**候选人**身份应答（可补充论证、回应新的质询）：",
        "examiner": "你继续以**答辩评委**身份质询（提出 1-2 个新的尖锐问题，聚焦具体证据）：",
        "panel": "你继续以**答辩委员会**身份回应（可补充合议意见、细化修改意见）：",
        "assistant": "你作为中立专家，结合已有答辩回应：",
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

    system_prompt = f"""你是一位学术论文答辩参与者，正在继续一场关于以下选题的答辩。

候选选题：{topic}

【Script 证据——系统预计算的确定性统计，非你的判断；引用时必须原样复述，标注为系统统计】
{script_evidence}

【召回论文列表（按相似度降序；[n] 编号即引用编号，仅限 [1]-[{len(papers[:30])}]）】
{papers_text}

【已进行的答辩环节】
{history_text or "（无）"}

{role_instruction}

【写作纪律】
- 回应要落到具体证据：关键判断先给量化依据（Script 数字或 [n] 编号）再展开；
- Script 数字原样引用；[n] 只引用上方列表内的论文，严禁编造；
- 证据不足时如实说明并降低置信度；
- 用中文作答，markdown 格式，300-700 字。"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
