"""系统设置与健康/统计接口。"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.config import settings
from app.ai_service import ai_trend_service
from app.routers.deps import verify_token

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


class TestModelRequest(BaseModel):
    model: str  # 'provider/model'


class FetchModelsRequest(BaseModel):
    name: Optional[str] = None    # 自定义 provider 名（编辑时用于回退已存的 key）
    base_url: str
    api_key: Optional[str] = None


@router.post("/settings/fetch-models")
async def fetch_provider_models(body: FetchModelsRequest, token: bool = Depends(verify_token)):
    """拉取 OpenAI 兼容 provider 的模型列表（GET {base_url}/models），供自定义配置时填充模型。

    api_key 为空时按 name 回退到已保存的 key（编辑自定义 provider 时前端不持有明文 key）。
    """
    from app.ai_service import _build_openai_client
    base_url = (body.base_url or "").strip()
    if not base_url:
        raise HTTPException(status_code=400, detail="base_url is required")

    api_key = (body.api_key or "").strip()
    if not api_key and body.name:
        for p in settings.get_custom_providers():
            if p.get("name") == body.name and p.get("api_key"):
                api_key = p["api_key"]
                break
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")

    try:
        client = _build_openai_client(api_key, base_url)
        models = await asyncio.to_thread(lambda: list(client.models.list()))
        ids = [getattr(m, "id", None) for m in models if getattr(m, "id", None)]
        if not ids:
            return {"models": [], "message": "provider 未返回可用模型"}
        return {"models": ids}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Fetch models failed for {base_url}: {e}")
        raise HTTPException(status_code=400, detail=f"获取模型列表失败：{e}")


@router.post("/settings/test-model")
async def test_model_link(body: TestModelRequest, token: bool = Depends(verify_token)):
    """OpenAI 兼容链接测试：向指定模型发送最小请求，验证 base_url/api_key/model 是否可用。"""
    try:
        provider, bare_model = ai_trend_service._resolve_model(body.model)
        client, _used_provider = ai_trend_service.get_client(provider)
    except KeyError as e:
        return {"ok": False, "model": body.model, "message": f"Provider 未配置或不可用：{e}"}
    if not bare_model:
        return {"ok": False, "model": body.model, "message": "缺少模型名"}
    start = time.time()
    try:
        await asyncio.to_thread(
            client.chat.completions.create,
            model=bare_model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
        )
        latency_ms = int((time.time() - start) * 1000)
        return {"ok": True, "model": body.model, "latency_ms": latency_ms,
                "message": f"连接成功，模型响应正常（{latency_ms}ms）"}
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        logger.warning(f"Model link test failed for {body.model}: {e}")
        return {"ok": False, "model": body.model, "latency_ms": latency_ms,
                "message": f"连接失败：{e}"}


class UpdateSettingsRequest(BaseModel):
    api_keys: Optional[dict] = None
    model_priority: Optional[List[str]] = None
    default_model: Optional[str] = None
    embedding_model: Optional[str] = None
    ports: Optional[dict] = None
    app_name: Optional[str] = None
    custom_providers: Optional[List[dict]] = None
    cnki_url_prefix: Optional[str] = None


def _mask_api_key(key: Optional[str]) -> str:
    if not key:
        return ""
    if len(key) > 8:
        return key[:4] + "****" + key[-4:]
    return "****"


@router.get("/settings")
async def get_settings_endpoint(token: bool = Depends(verify_token)):
    from app.config import Settings
    # 手动编辑 .env 后无需重启：每次读取前从 .env 重新同步运行时配置
    # （update_setting 写入的键同样在 .env 中，重读不会丢失；环境变量优先级高于 .env，行为不变）
    try:
        fresh = Settings()
        for _k, _v in fresh.model_dump().items():
            setattr(settings, _k, _v)
    except Exception as e:  # 同步失败时退回内存配置，保证接口可用
        logger.warning(f"refresh settings from .env failed: {e}")
    api_keys = {
        "zhipu": {
            "configured": bool(settings.zhipu_api_key),
            "masked": _mask_api_key(settings.zhipu_api_key),
        },
        "openai": {
            "configured": bool(settings.openai_api_key),
            "masked": _mask_api_key(settings.openai_api_key),
        },
        "siliconflow": {
            "configured": bool(settings.siliconflow_api_key),
            "masked": _mask_api_key(settings.siliconflow_api_key),
        },
    }
    models = ai_trend_service.get_model_status()
    from app.main import scheduler
    scheduler_info = {
        "running": scheduler.is_running(),
        "jobs": scheduler.get_jobs_info(),
    }
    api_token_configured = bool(settings.api_token)

    # Get custom providers
    custom_providers = settings.get_custom_providers()
    custom_providers_status = []
    for cp in custom_providers:
        custom_providers_status.append({
            "name": cp.get("name", ""),
            "base_url": cp.get("base_url", ""),
            "api_key_configured": bool(cp.get("api_key")),
            "api_key_masked": _mask_api_key(cp.get("api_key")),
            "models": cp.get("models", []),
        })

    return {
        "api_keys": api_keys,
        "models": models,
        "scheduler": scheduler_info,
        "api_token_configured": api_token_configured,
        "ports": {
            "backend": settings.backend_port,
            "frontend": settings.frontend_port,
        },
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "custom_providers": custom_providers_status,
        "default_model": settings.default_model,
        "embedding_model": settings.embedding_model,
        "cnki_url_prefix": settings.cnki_url_prefix,
    }


@router.put("/settings")
async def update_settings_endpoint(
    body: UpdateSettingsRequest,
    token: bool = Depends(verify_token)
):
    from app.config import Settings
    keys_changed = False
    models_changed = False

    if body.api_keys:
        key_mapping = {
            "zhipu": "zhipu_api_key",
            "openai": "openai_api_key",
            "siliconflow": "siliconflow_api_key",
        }
        for provider, value in body.api_keys.items():
            env_key = key_mapping.get(provider)
            if env_key and value is not None:
                Settings.update_setting(env_key, value)
                keys_changed = True

    if body.model_priority:
        # 自定义 Provider 的模型顺序写回其配置；内置 Provider 的顺序由 update_models 持久化
        custom_names = {p.get("name") for p in settings.get_custom_providers()}
        custom_order = {}
        for m in body.model_priority:
            provider = m.split("/", 1)[0]
            if provider in custom_names:
                custom_order.setdefault(provider, []).append(m.split("/", 1)[1])
        if custom_order:
            providers = settings.get_custom_providers()
            for p in providers:
                if p.get("name") in custom_order and custom_order[p["name"]]:
                    p["models"] = custom_order[p["name"]]
            Settings.update_setting("custom_providers", json.dumps(providers, ensure_ascii=False))
            keys_changed = True  # 触发 reload 以重新加载自定义 Provider 的模型列表
        ai_trend_service.update_models(body.model_priority)
        models_changed = True

    if body.ports:
        for port_key, port_value in body.ports.items():
            if port_key in ("backend_port", "frontend_port"):
                Settings.update_setting(port_key, str(port_value))

    if body.app_name is not None:
        Settings.update_setting("app_name", body.app_name)

    if body.cnki_url_prefix is not None:
        Settings.update_setting("cnki_url_prefix", body.cnki_url_prefix.strip())

    if body.default_model is not None:
        Settings.update_setting("default_model", body.default_model)

    if body.embedding_model is not None:
        Settings.update_setting("embedding_model", body.embedding_model)
        keys_changed = True  # 触发 reload 以加载 embedding 对应的 provider 客户端

    if body.custom_providers is not None:
        # 保存自定义 provider：api_key 为空时继承已有同名 provider 的 key（支持编辑时保留原 key）
        current = {p.get("name"): p for p in settings.get_custom_providers()}
        seen = set()
        valid_providers = []
        for p in body.custom_providers:
            name = (p.get("name") or "").strip()
            base_url = (p.get("base_url") or "").strip()
            if not name or not base_url or name in seen:
                continue
            api_key = p.get("api_key") or ""
            if not api_key:
                api_key = current.get(name, {}).get("api_key", "")
            if not api_key:
                continue  # 新增且未提供 key → 丢弃
            models = [m for m in (p.get("models") or []) if isinstance(m, str) and m.strip()]
            seen.add(name)
            valid_providers.append({"name": name, "base_url": base_url, "api_key": api_key, "models": models})
        Settings.update_setting("custom_providers", json.dumps(valid_providers, ensure_ascii=False))
        keys_changed = True

    if keys_changed:
        ai_trend_service.reload()

    return {"status": "ok", "keys_changed": keys_changed, "models_changed": models_changed}


@router.get("/stats")
async def get_system_stats(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text as sa_text

    try:
        result = await db.execute(sa_text("""
            SELECT
                (SELECT COUNT(*) FROM papers) AS total_papers,
                (SELECT COUNT(DISTINCT journal_name) FROM papers WHERE journal_name IS NOT NULL) AS journal_count,
                (SELECT COUNT(DISTINCT keywords_cn) FROM papers WHERE keywords_cn IS NOT NULL) AS keyword_count,
                (SELECT created_at FROM papers ORDER BY created_at DESC LIMIT 1) AS latest_created_at,
                (SELECT created_at FROM crawl_logs ORDER BY created_at DESC LIMIT 1) AS latest_crawl_at
        """))
        row = result.fetchone()
        total_papers = row[0]
        journal_count = row[1]
        keyword_count = row[2]
        latest_created_at = row[3]
        latest_crawl_at = row[4]

        result = await db.execute(sa_text("""
            SELECT 'source' AS kind, source AS key, COUNT(*) AS cnt FROM papers GROUP BY source
            UNION ALL
            SELECT 'year' AS kind, CAST(SUBSTR(published_at, 1, 4) AS TEXT) AS key, COUNT(*) AS cnt
            FROM papers WHERE published_at IS NOT NULL GROUP BY SUBSTR(published_at, 1, 4)
        """))
        source_counts = {}
        year_counts = {}
        for row in result:
            if row[0] == 'source':
                source_counts[row[1]] = row[2]
            else:
                year_counts[row[1]] = row[2]

        result = await db.execute(sa_text("""
            SELECT journal_name, COUNT(*) AS cnt
            FROM papers
            WHERE journal_name IS NOT NULL
            GROUP BY journal_name
            ORDER BY cnt DESC
            LIMIT 10
        """))
        top_journals = {}
        for row in result:
            top_journals[row[0]] = row[1]

        from app.config import BASE_DIR
        db_path = BASE_DIR / "data" / "paperpulse.db"
        db_size_mb = 0.0
        if db_path.exists():
            db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)

        from app.main import scheduler
        scheduler_running = scheduler.is_running()

        ai_usage_result = await db.execute(sa_text("""
            SELECT 
                COUNT(*) as total_analyses,
                COALESCE(SUM(tokens_used), 0) as total_tokens,
                COALESCE(SUM(processing_time_ms), 0) as total_processing_ms,
                COALESCE(SUM(total_papers), 0) as total_papers_analyzed
            FROM ai_analysis_reports 
            WHERE status = 'success'
        """))
        ai_usage_row = ai_usage_result.fetchone()

        ai_by_model_result = await db.execute(sa_text("""
            SELECT model, COUNT(*) as count, COALESCE(SUM(tokens_used), 0) as tokens
            FROM ai_analysis_reports 
            WHERE status = 'success'
            GROUP BY model
        """))
        ai_by_model = [{"model": row[0], "count": row[1], "tokens": row[2]} for row in ai_by_model_result.fetchall()]

        return {
            "app_name": settings.app_name,
            "app_version": settings.app_version,
            "total_papers": total_papers,
            "journal_count": journal_count,
            "keyword_count": keyword_count,
            "latest_paper_at": str(latest_created_at) if latest_created_at else None,
            "latest_crawl_at": str(latest_crawl_at) if latest_crawl_at else None,
            "source_counts": source_counts,
            "year_counts": year_counts,
            "top_journals": top_journals,
            "db_size_mb": db_size_mb,
            "scheduler_running": scheduler_running,
            "ai_usage": {
                "total_analyses": ai_usage_row[0],
                "total_tokens": ai_usage_row[1],
                "total_processing_ms": ai_usage_row[2],
                "total_papers_analyzed": ai_usage_row[3],
                "by_model": ai_by_model,
            },
        }
    except Exception as e:
        logger.error(f"Failed to get system stats: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error ({type(e).__name__})")


@router.get("/data-health")
async def get_data_health(db: AsyncSession = Depends(get_db)):
    """数据健康中心聚合状态：embedding(向量覆盖) / trend(趋势分析) / similarity(论文相关性)。

    统一供系统管理-数据页一次拉取三块状态；相关的"一键动作"（补齐向量、
    刷新趋势、重算相似度）由各自既有接口触发。
    """
    from sqlalchemy import select as sa_select, func as sa_func
    from app.models import PaperFeatures, TopicTrend, PaperSimilarity

    # 1) 向量覆盖（复用 topic-validator/status 的同款统计）
    embedded = (await db.execute(
        sa_select(sa_func.count(PaperFeatures.id)).where(PaperFeatures.embedding.isnot(None))
    )).scalar() or 0
    total_feats = (await db.execute(
        sa_select(sa_func.count(PaperFeatures.id))
    )).scalar() or 0

    # 2) 趋势分析情况（topic_trends 表覆盖度与最近生成）
    trend_topics = (await db.execute(
        sa_select(sa_func.count(sa_func.distinct(TopicTrend.topic)))
    )).scalar() or 0
    trend_records = (await db.execute(
        sa_select(sa_func.count(TopicTrend.id))
    )).scalar() or 0
    latest_week = (await db.execute(
        sa_select(sa_func.max(TopicTrend.week_start))
    )).scalar()
    latest_trend_update = (await db.execute(
        sa_select(sa_func.max(TopicTrend.created_at))
    )).scalar()

    # 3) 论文内容相关性（paper_similarities 覆盖 + 是否正在重算）
    sim_pairs = (await db.execute(
        sa_select(sa_func.count(PaperSimilarity.id))
    )).scalar() or 0
    sim_papers = (await db.execute(
        sa_select(sa_func.count(sa_func.distinct(PaperSimilarity.paper_id_a)))
    )).scalar() or 0
    latest_sim = (await db.execute(
        sa_select(sa_func.max(PaperSimilarity.computed_at))
    )).scalar()

    from app.routers.crawler import _similarity_task_state
    similarity_running = bool(_similarity_task_state.get("running"))

    return {
        "embedding": {
            "embedded": embedded,
            "total": total_feats,
            "missing": max(total_feats - embedded, 0),
        },
        "trend": {
            "topics": trend_topics,
            "records": trend_records,
            "latest_week_start": str(latest_week) if latest_week else None,
            "latest_updated_at": str(latest_trend_update) if latest_trend_update else None,
        },
        "similarity": {
            "pairs": sim_pairs,
            "covered_papers": sim_papers,
            "latest_computed_at": str(latest_sim) if latest_sim else None,
            "running": similarity_running,
        },
    }


