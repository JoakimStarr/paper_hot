"""选题验证技能：两阶段检索证据 -> 盲态预承诺评分 -> 结构化结论 + markdown 报告。

相对旧版 prompt 的三个强化：
1. 盲态预承诺（academic-paper 生成器-评估器契约）：新颖性/拥挤度的评分档位由本模块
   固定写死（RUBRIC），模型只能按档位归档并在正文引用所落阈值——摧毁"先看证据再
   找理由"的漂移路径；
2. [Script]/[LLM] 证据分离（paper-audit 模式）：召回统计与竞争地图由后端确定性计算，
   以「Script 证据」块注入，模型判断必须与该块对齐，不得复述为自身结论；
3. 结构化输出契约：输出以 ```json 头开始（novelty/crowding/feasibility/gate），
   后端 split_json_head 解析后直接回填项目字段；无 JSON 头时降级为纯 markdown
   （旧格式兼容，前端正则解析仍生效）。

正文强制包含「未找到的证据」声明（literature-review 模式）：禁止用沉默冒充"没人做过"。
"""
import json
import re
from typing import Any, Dict, List, Optional, Tuple

NAME = "validate"
DESCRIPTION = "选题验证：预承诺评分标准 + Script 证据 + 结构化结论（novelty/crowding/feasibility/gate）"

# 输出 JSON 头的合法取值
CROWDING_LEVELS = ("低", "中", "高")
GATES = ("pass", "caution", "avoid")

_JSON_DECODER = json.JSONDecoder()

# ---- 盲态预承诺评分标准（系统固定；模型只能归档，不得自造标准） ----
RUBRIC = """【评分标准——系统预承诺，评审不得偏离；正文打分时必须引用所落档位的阈值】
新颖性 novelty（1-10）按召回证据的最高相似度 max_similarity 归档：
- [1-3] max_similarity ≥ 0.90：库内已存在近乎同题的研究，属撞题级重合
- [4-6] 0.75 ≤ max_similarity < 0.90：核心组合已被研究过，仅剩表述/对象差异
- [7-8] 0.60 ≤ max_similarity < 0.75：方向存在研究，但具体机制/对象/数据组合未被覆盖
- [9-10] max_similarity < 0.60：库内无近似研究（需在「未找到的证据」中说明检索局限）
拥挤度 crowding（低/中/高）按近一年发表量 recent_1y_count 与 top30 平均相似度归档：
- 高：recent_1y_count ≥ 15 或 top30_avg_similarity ≥ 0.80（大量团队在快速灌该方向）
- 中：5 ≤ recent_1y_count < 15 且 top30_avg_similarity < 0.80（有稳定产出但未饱和）
- 低：recent_1y_count < 5 且 top30_avg_similarity < 0.75（明显稀疏）
可行性 feasibility（1-10）按公开数据可得性与方法成熟度评估：依赖微观数据申请/私有不公开数据 ≤ 4；
公开数据库（CSMAR/Wind/CFPS 等）可支撑 5-8；公开数据 + 成熟方法 9-10。
gate 总门控：只有「撞题级重合」（novelty ≤ 3）判 avoid；方向拥挤但仍有差异化空间判 caution；其余 pass。
注意：若召回为空或证据明显不足，按证据下限打分并在正文显著降低置信度，而不是凭空给高分。"""


def build_script_evidence(stats: dict, competition: dict) -> str:
    """把后端确定性计算（_crowding_stats / _competition_map）格式化为 Script 证据块。

    这部分不是模型判断：正文若引用这些数字，应标注为系统统计而非"分析得出"。
    """
    comp = competition or {}
    authors = ", ".join(a.get("name", "") for a in comp.get("top_authors", [])[:8]) or "无"
    journals = ", ".join(j.get("journal", "") for j in comp.get("journal_distribution", [])[:8]) or "无"
    return (
        f"- 召回模式: {stats.get('mode', '?')}（Script：检索管线确定性产出）\n"
        f"- Top30 平均相似度: {stats.get('top30_avg_similarity', 0)}\n"
        f"- 最高相似度 max_similarity: {stats.get('max_similarity', 0)}\n"
        f"- 近 3 个月发表: {stats.get('recent_3m_count', 0)} 篇\n"
        f"- 近一年发表 recent_1y_count: {comp.get('recent_1y_count', 0)} 篇\n"
        f"- 高频关键词: {', '.join(k.get('keyword', '') for k in stats.get('keyword_overlap', [])[:8]) or '无'}\n"
        f"- 活跃作者（Script 统计）: {authors}\n"
        f"- 主要发表期刊（Script 统计）: {journals}"
    )


def build_papers_text(papers: List[dict], limit: int = 30) -> str:
    """召回论文 -> 编号文本（[n] 编号即输出引用编号，与前端召回卡片对齐）。"""
    lines = []
    for i, p in enumerate(papers[:limit]):
        pub = str(p.get("published_at"))[:10] if p.get("published_at") else "?"
        kws = ", ".join((p.get("keywords") or [])[:5]) or "无"
        lines.append(
            f"[{i + 1}] ({p.get('similarity', 0):.3f}) {p.get('title', '')} "
            f"({p.get('source', '?')}, {pub}) 关键词: {kws}"
        )
    return "\n".join(lines) or "（未召回近似论文：该题目的表述在库内近乎无匹配）"


def build_messages(topic: str, papers: List[dict], stats: dict, competition: dict) -> List[dict]:
    """构造验证 prompt：预承诺标准 + Script 证据 + 召回列表 + 输出契约。"""
    papers_text = build_papers_text(papers)
    script_evidence = build_script_evidence(stats, competition)
    system_prompt = f"""你是一位严格的学术选题评审专家。基于下方检索证据评估候选选题。

候选选题：{topic}

【Script 证据——系统预计算的确定性统计，非你的判断；你的结论必须与之一致】
{script_evidence}

{RUBRIC}

【召回论文列表（按相似度降序；[n] 编号即引用编号）】
{papers_text}

【输出契约——严格遵守】
1. 第一行输出 ```json 代码块（之后才是正文）：
{{
  "novelty": 1-10 的整数,
  "crowding": "低|中|高",
  "feasibility": 1-10 的整数,
  "gate": "pass|caution|avoid"
}}
2. 正文用 markdown，依次包含以下小节（顺序固定）：
## 新颖性评估
按预承诺档位归档打分，引用所落阈值与具体论文 [n] 依据。
## 竞争拥挤度
对照 recent_1y_count 与平均相似度阈值归档，指认最活跃的作者/期刊（引用 Script 统计）。
## 机会窗口
综合判断：蓝海 / 正在升温 / 红海，给进入时机结论。
## 风险与盲区
必须包含「未找到的证据」小节：明确列出检索可能遗漏什么（关键词表述差异、跨领域文献、英文文献），
并给出整体置信度（高/中/低）。禁止用检索沉默冒充"没有人做过"。
## 建议切入角度
与已召回论文差异化的 2-3 个具体切入点。
## 结论
gate 判定 + 一句话理由。

要求：诚实、量化、不客套；证据不足时明确降低置信度。"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请验证选题：「{topic}」"},
    ]


def normalize_scores(data: Any) -> Dict[str, Any]:
    """钳制 JSON 头字段到合法域；非法值丢弃（降级为不回填）。"""
    if not isinstance(data, dict):
        return {}
    out: Dict[str, Any] = {}
    try:
        n = int(data.get("novelty"))
        if 1 <= n <= 10:
            out["novelty"] = n
    except (TypeError, ValueError):
        pass
    try:
        f = int(data.get("feasibility"))
        if 1 <= f <= 10:
            out["feasibility"] = f
    except (TypeError, ValueError):
        pass
    if data.get("crowding") in CROWDING_LEVELS:
        out["crowding"] = data["crowding"]
    if data.get("gate") in GATES:
        out["gate"] = data["gate"]
    return out


def split_json_head(content: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """从流式正文中剥离开头的 JSON 头（围栏无关）。

    - 标准形态：```json {...} ``` 围栏包裹；
    - 模型常省略闭合围栏（glm-4.5-flash 实测）：只要 { 对象本身完整即用
      JSONDecoder.raw_decode 解析，不依赖闭合 ```；
    - 解析失败 / 字段全非法 → 返回 (None, 原文)，降级为旧版纯 markdown 流程。
    """
    text = content or ""
    stripped = text.lstrip()
    if not stripped.startswith("```json") and not stripped.startswith("{"):
        return None, text
    brace = text.find("{")
    if brace < 0:
        return None, text
    try:
        obj, end = _JSON_DECODER.raw_decode(text, brace)
    except ValueError:
        return None, text
    if not isinstance(obj, dict):
        return None, text
    scores = normalize_scores(obj)
    if not scores:
        return None, text
    tail = text[end:].lstrip()
    if tail.startswith("```"):
        nl = tail.find("\n")
        tail = tail[nl + 1:] if nl >= 0 else ""
    return scores, tail.lstrip("\n")


def head_in_progress(content: str) -> bool:
    """缓冲文本是否仍是「进行中的 JSON 头」：以 ```json / { 开头且尚未超长。

    流式判定期据此决定继续缓冲还是放弃（放行原文）。
    """
    stripped = (content or "").lstrip()
    return (stripped.startswith("```json") or stripped.startswith("{")) and len(content) < 8192


def apply_scores(project, scores: Dict[str, Any]) -> List[str]:
    """把解析出的评分回填到项目对象（就地 setattr，不 commit）；返回更新的字段名。

    状态流转克制：仅当项目仍在 to_validate 时推进到 validated，
    不覆盖用户手动设置的 subscribed / abandoned。
    """
    touched: List[str] = []
    if scores.get("novelty") is not None:
        project.novelty = scores["novelty"]
        touched.append("novelty")
    if scores.get("crowding"):
        project.crowding = scores["crowding"]
        touched.append("crowding")
    if scores.get("feasibility") is not None:
        project.feasibility = scores["feasibility"]
        touched.append("feasibility")
    if project.status == "to_validate":
        project.status = "validated"
        touched.append("status")
    return touched
