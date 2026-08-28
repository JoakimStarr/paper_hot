"""选题灵感向导：一句话想法 + 偏好 → AI 生成/迭代候选选题（无状态）。

流程落点：选题灵感 → 输入想法 → AI 推荐选题方向 + 参考文献 → 选题定义。

- POST /topic-ideas/generate：首轮生成或迭代轮（带 feedback/previous_candidates）。
  每个候选方向附带：
  - keywords：检索关键词（选题拆分，供「验证」步知网关键词爬虫 / 文献检索使用）
  - references：库内相关文献（embedding 召回，杜绝 LLM 编造文献）

不建表、不做会话持久化；迭代上下文由前端持有并回传。
"""
import asyncio
import logging
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.deps import verify_token
from app.routers.topic import _retrieve_similar_papers
from app.routers.workbench import _llm_json

logger = logging.getLogger(__name__)
router = APIRouter()

MIN_CANDIDATES = 4
MAX_CANDIDATES = 6
REFERENCE_PER_CANDIDATE = 3

_IDENTITY_LABELS = {"bachelor": "本科生开题", "master": "硕士论文", "phd": "博士论文", "faculty": "科研投稿"}
_PAPER_TYPE_LABELS = {"empirical": "实证研究", "review": "文献综述", "case": "案例研究", "theory": "理论研究"}
_VENUE_LABELS = {"cn_top": "中文顶刊", "cn_regular": "中文普通期刊", "en_top": "英文顶刊", "any": "不限"}


# ---------------------------------------------------------------- 纯函数（可测）

def _build_preferences_text(pref: Optional[BaseModel]) -> str:
    """偏好对象 → 自然语言文本（可测纯函数）。"""
    if not pref:
        return ""
    lines = []
    if getattr(pref, "identity", None):
        lines.append(f"身份：{_IDENTITY_LABELS.get(pref.identity, pref.identity)}")
    if getattr(pref, "paper_type", None):
        lines.append(f"论文类型：{_PAPER_TYPE_LABELS.get(pref.paper_type, pref.paper_type)}")
    if getattr(pref, "subfields", None):
        lines.append("倾向子领域：" + "、".join(pref.subfields))
    if getattr(pref, "methods", None):
        lines.append("方法偏好：" + "、".join(pref.methods))
    if getattr(pref, "data", None):
        lines.append("数据偏好：" + "、".join(pref.data))
    if getattr(pref, "venue", None):
        lines.append(f"期刊定位：{_VENUE_LABELS.get(pref.venue, pref.venue)}")
    novelty = getattr(pref, "prefer_novelty", None)
    if novelty is not None:
        n = max(0.0, min(1.0, float(novelty)))
        if n >= 0.7:
            lines.append("偏好：更强调新颖度")
        elif n <= 0.3:
            lines.append("偏好：更强调可行性")
        else:
            lines.append("偏好：新颖度与可行性均衡")
    if getattr(pref, "focus_china", True):
        lines.append("聚焦中国情境")
    extra = (getattr(pref, "extra", "") or "").strip()
    if extra:
        lines.append("其他要求：" + extra)
    return "\n".join(lines)


def _clamp_int(v, lo: int = 0, hi: int = 5) -> int:
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return 0


def _norm_str_list(value, limit: int) -> List[str]:
    if not isinstance(value, list):
        return []
    out = []
    for x in value:
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def _normalize_candidates(raw) -> List[dict]:
    """LLM 输出 → 规范化候选列表（数量钳制、字段兜底、assessment 数值钳制）。"""
    if isinstance(raw, dict):
        raw = raw.get("candidates", raw.get("topics", []))
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        rqs = _norm_str_list(item.get("research_questions") or item.get("questions"), 4)
        assessment_raw = item.get("assessment")
        if not isinstance(assessment_raw, dict):
            assessment_raw = {}
        assessment = {
            "novelty": _clamp_int(assessment_raw.get("novelty", 3)),
            "feasibility": _clamp_int(assessment_raw.get("feasibility", 3)),
            "literature_support": _clamp_int(
                assessment_raw.get("literature_support", assessment_raw.get("literature", 3))
            ),
            "comment": str(assessment_raw.get("comment") or "")[:120],
        }
        out.append({
            "title": title,
            "research_questions": rqs,
            "hypothesis": str(item.get("hypothesis") or "")[:200],
            "why": str(item.get("why") or "")[:300],
            "angle": str(item.get("angle") or "")[:200],
            "methods": _norm_str_list(item.get("methods"), 4),
            "data": _norm_str_list(item.get("data"), 4),
            "subfield": str(item.get("subfield") or "")[:50],
            "keywords": _norm_str_list(item.get("keywords"), 6),
            "assessment": assessment,
            "references": [],
        })
    return out[:MAX_CANDIDATES]


async def _attach_references(db: AsyncSession, candidates: List[dict]) -> List[dict]:
    """为每个候选方向召回库内相关文献（embedding，真实文献杜绝编造）。失败降级为空。"""

    async def _one(c: dict) -> None:
        try:
            papers, _mode = await _retrieve_similar_papers(db, c["title"], k=REFERENCE_PER_CANDIDATE)
            refs = []
            for b in papers:
                refs.append({
                    "id": b["id"],
                    "title": b.get("title") or "",
                    "journal": b.get("journal_name") or b.get("source") or "",
                    "published_at": str(b.get("published_at") or "")[:10] or None,
                    "similarity": round(float(b.get("similarity") or 0), 4),
                })
            c["references"] = refs[:REFERENCE_PER_CANDIDATE]
        except Exception as e:
            logger.warning(f"attach references for '{c['title']}' failed: {e}")
            c["references"] = []

    await asyncio.gather(*(_one(c) for c in candidates))
    return candidates


async def _build_profile_lines(db: AsyncSession, uid: str) -> List[str]:
    """用户画像文本：关注子领域/关键词 + 最近阅读 + 库内空白 + 热点（复用 recommend 聚合思路）。"""
    from sqlalchemy import select as sa_select, func as sa_func

    from app.models import FollowedSubfield, FollowedKeyword, ReadingHistory, Paper, TopicTrend

    lines = []
    try:
        sf = (await db.execute(
            sa_select(FollowedSubfield.subfield).where(FollowedSubfield.user_id == uid)
        )).scalars().all()
        if sf:
            lines.append("关注的子领域：" + "、".join(sf))
        kw = (await db.execute(
            sa_select(FollowedKeyword.keyword).where(FollowedKeyword.user_id == uid)
        )).scalars().all()
        if kw:
            lines.append("关注的关键词：" + "、".join(kw))
        recent = (await db.execute(
            sa_select(Paper.title)
            .join(ReadingHistory, ReadingHistory.paper_id == Paper.id)
            .where(ReadingHistory.user_id == uid)
            .order_by(ReadingHistory.read_at.desc())
            .limit(6)
        )).scalars().all()
        if recent:
            lines.append("最近在读：" + "；".join(recent))
    except Exception as e:
        logger.warning(f"build profile lines failed: {e}")

    try:
        from app.stats import compute_keyword_gaps
        gaps = await compute_keyword_gaps(db, limit=6)
        if gaps:
            lines.append("库内研究空白：" + "；".join(f"{g['source']}×{g['target']}" for g in gaps))
    except Exception:
        pass
    try:
        hot_rows = (await db.execute(
            sa_select(TopicTrend.topic, sa_func.sum(TopicTrend.paper_count))
            .group_by(TopicTrend.topic)
            .order_by(sa_func.sum(TopicTrend.paper_count).desc())
            .limit(6)
        )).all()
        if hot_rows:
            lines.append("库内热点方向：" + "；".join(f"{t}({int(c or 0)}篇)" for t, c in hot_rows))
    except Exception:
        pass
    return lines


# ---------------------------------------------------------------- 请求/响应模型

class TopicIdeaPreferences(BaseModel):
    identity: Optional[str] = None        # bachelor | master | phd | faculty
    paper_type: Optional[str] = None      # empirical | review | case | theory
    subfields: List[str] = []
    methods: List[str] = []
    data: List[str] = []
    venue: Optional[str] = None           # cn_top | cn_regular | en_top | any
    prefer_novelty: float = 0.5           # 0~1 新颖度 vs 可行性
    focus_china: bool = True
    extra: str = ""


class PreviousCandidate(BaseModel):
    title: str = ""
    research_questions: List[str] = []


class TopicIdeaGenerateRequest(BaseModel):
    idea: str
    preferences: Optional[TopicIdeaPreferences] = None
    feedback: Optional[str] = None
    previous_candidates: List[PreviousCandidate] = []


# ---------------------------------------------------------------- 端点

# 生成任务（进程内）：LLM 单次 50s+，远超 dev 代理 30s 上限，必须后台跑 + 前端轮询。
_generate_tasks: dict = {}
_TASK_TTL_SECONDS = 10 * 60


def _cleanup_generate_tasks() -> None:
    now = time.time()
    expired = [k for k, v in _generate_tasks.items() if now - v["created_at"] > _TASK_TTL_SECONDS]
    for k in expired:
        _generate_tasks.pop(k, None)


async def _generate_candidates(
    db: AsyncSession, body: TopicIdeaGenerateRequest, uid: str,
    on_phase: Optional[callable] = None,
) -> dict:
    """核心生成逻辑：一句话想法 + 偏好 → 4-6 个候选（方向 + 检索关键词 + 库内参考文献）。

    带 feedback / previous_candidates 时为迭代轮：注入上一轮候选避免雷同，并回应调整指令。
    失败抛 HTTPException（503 AI 失败 / 400 idea 为空）。
    on_phase 可选回调：阶段推进时调用 on_phase("generating") / on_phase("recalling")，
    供后台任务向轮询端点暴露当前阶段。
    """
    idea = (body.idea or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="idea is required")

    if on_phase:
        on_phase("generating")

    pref_text = _build_preferences_text(body.preferences)
    profile_lines = await _build_profile_lines(db, uid)

    iter_block = ""
    if body.previous_candidates:
        prev_titles = "\n".join(f"- {c.title}" for c in body.previous_candidates if c.title)
        if prev_titles:
            iter_block += f"上一轮候选选题：\n{prev_titles}\n"
        if body.feedback and body.feedback.strip():
            iter_block += f"用户调整指令：{body.feedback.strip()}\n"
        if iter_block:
            iter_block += "要求：本轮必须明显区别于上一轮候选，并完整回应调整指令。\n"

    system_prompt = (
        "你是经济管理领域的学术选题顾问，擅长把一句话想法打磨成具体、可研究、可发表的学术选题。"
        "回答使用中文，输出严格 JSON（不要 markdown 代码块）。"
    )
    user_prompt = f"""用户的一句话想法：{idea}

用户偏好：
{pref_text or "（未提供，按通用经管方向推荐）"}

用户画像：
{chr(10).join(profile_lines) or "（暂无画像）"}

{iter_block}请基于以上信息推荐 {MIN_CANDIDATES}-{MAX_CANDIDATES} 个具体选题。输出 JSON 对象：
{{"candidates": [
  {{
    "title": "具体题目（含研究对象、作用机制、场景或数据，禁止模板化如「XX与YY的交叉研究」）",
    "research_questions": ["研究问题1", "研究问题2"],
    "hypothesis": "初步假设",
    "why": "为什么值得做/创新点（结合偏好与画像）",
    "angle": "切入角度或数据方案",
    "methods": ["方法1", "方法2"],
    "data": ["数据源1"],
    "subfield": "所属子领域",
    "keywords": ["3-6个检索关键词，用于后续文献检索与爬虫拆分"],
    "assessment": {{"novelty": 0-5, "feasibility": 0-5, "literature_support": 0-5, "comment": "一句话点评"}}
  }}
]}}

要求：
1. 每个候选必须具体可检验，标题含对象/机制/场景
2. 候选之间要有区分度（不同机制/对象/数据）
3. keywords 是拆分选题用的检索词，覆盖研究对象、机制与场景，便于知网/文献检索
4. 贴合用户偏好与画像；结合库内空白与热点机会
5. assessment 用于帮助用户决策，评论精炼"""

    try:
        data = await _llm_json(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            # max_tokens=8192：本 prompt 较长（完整 JSON schema + 6 候选），默认模型为推理模型
            # 时 reasoning_content 大量占用预算，4096 会被 finish_reason=length 截断导致 JSON 解析失败。
            max_tokens=8192, temperature=0.6,
        )
    except Exception as e:
        logger.warning(f"topic-ideas generate failed: {e}")
        raise HTTPException(status_code=503, detail="AI 生成失败，请重试")

    candidates = _normalize_candidates(data)
    if not candidates:
        raise HTTPException(status_code=503, detail="AI 生成失败，请重试")

    # 候选方向 → 库内参考文献（真实文献，杜绝编造；并行召回）
    if on_phase:
        on_phase("recalling")
    candidates = await _attach_references(db, candidates)

    round_no = 2 if body.previous_candidates else 1
    for i, c in enumerate(candidates):
        c["id"] = f"r{round_no}c{i}"

    return {"round": round_no, "candidates": candidates}


@router.post("/topic-ideas/generate")
async def generate_topic_ideas(
    body: TopicIdeaGenerateRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    token: bool = Depends(verify_token),
):
    """一句话想法 + 偏好 → AI 生成候选选题（后台任务，返回 task_id 供轮询）。

    生成耗时可达 1 分钟+（推理模型长输出），前端经 Next 代理有 30s 上限，
    故拆为：POST 提交任务 → GET /topic-ideas/generate/{task_id} 轮询结果。
    """
    idea = (body.idea or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="idea is required")
    uid = (request.headers.get("x-user-id") if request else None) or "local"

    _cleanup_generate_tasks()
    task_id = uuid.uuid4().hex[:12]
    _generate_tasks[task_id] = {"status": "pending", "phase": "generating", "created_at": time.time()}

    from app.main import spawn_background_task
    spawn_background_task(_run_generate_task(task_id, body, uid))
    return {"task_id": task_id, "status": "pending", "phase": "generating"}


@router.get("/topic-ideas/generate/{task_id}")
async def get_generate_task(
    task_id: str,
    request: Request = None,
    token: bool = Depends(verify_token),
):
    """轮询生成任务结果：pending → 继续等；done → 返回候选；error → 携带原因。"""
    task = _generate_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期，请重新生成")
    if task["status"] == "done":
        return {"status": "done", "round": task.get("round"), "candidates": task.get("candidates"), "phase": task.get("phase")}
    if task["status"] == "error":
        return {"status": "error", "error": task.get("error") or "AI 生成失败，请重试", "phase": task.get("phase")}
    return {"status": "pending", "phase": task.get("phase")}


async def _run_generate_task(task_id: str, body: TopicIdeaGenerateRequest, uid: str):
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            def _on_phase(phase: str) -> None:
                task = _generate_tasks.get(task_id)
                if task is not None:
                    task["phase"] = phase

            result = await _generate_candidates(db, body, uid, on_phase=_on_phase)
            _generate_tasks[task_id].update(
                {"status": "done", "round": result["round"], "candidates": result["candidates"]}
            )
        except HTTPException as e:
            logger.warning(f"topic-ideas task {task_id} failed: {e.detail}")
            _generate_tasks[task_id].update({"status": "error", "error": str(e.detail)})
        except Exception as e:
            logger.warning(f"topic-ideas task {task_id} unexpected error: {e}")
            _generate_tasks[task_id].update({"status": "error", "error": "AI 生成失败，请重试"})
