from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Float, JSON, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator
import uuid
import json as _json


class UnicodeJSON(TypeDecorator):
    # 用 Text 而非 JSON 作为底层实现：JSON impl 会对本类型已序列化的字符串再编码一次，
    # 导致 list/dict 被双重编码存成 '"[...]"'（历史数据 2484 篇即因此损坏）。
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            # 已是序列化后的 JSON 字符串：原样存储，避免二次编码
            try:
                _json.loads(value)
                return value
            except (_json.JSONDecodeError, TypeError):
                return _json.dumps(value, ensure_ascii=False)
        return _json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if value is None or not isinstance(value, str):
            return value
        try:
            result = _json.loads(value)
        except (_json.JSONDecodeError, TypeError):
            return value
        # 兼容历史双重编码数据（'"[\"...\"]"'）：内层仍是 JSON 字符串则再解一层
        if isinstance(result, str):
            try:
                inner = _json.loads(result)
                if isinstance(inner, (list, dict)):
                    return inner
            except (_json.JSONDecodeError, TypeError):
                pass
            return result
        return result
from app.database import Base
from app.config import settings


def get_uuid_column():
    if settings.database_url.startswith("sqlite"):
        return Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    else:
        from sqlalchemy.dialects.postgresql import UUID
        return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Paper(Base):
    __tablename__ = "papers"
    
    id = get_uuid_column()
    title = Column(String(500), nullable=False, index=True)
    abstract = Column(Text, nullable=False)
    authors = Column(UnicodeJSON, default=list)
    url = Column(String(500), nullable=False, unique=True)
    source = Column(String(50), nullable=False, index=True)
    venue = Column(String(100), nullable=True)
    published_at = Column(DateTime, nullable=True, index=True)
    discipline = Column(String(50), nullable=True, index=True)
    journal_name = Column(String(200), nullable=True, index=True)
    journal_issue = Column(String(100), nullable=True)
    economics_subfield = Column(String(100), nullable=True, index=True)
    cnki_subject = Column(String(500), nullable=True)
    doi = Column(String(200), nullable=True, unique=True)
    keywords_cn = Column(UnicodeJSON, default=list)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    features = relationship("PaperFeatures", back_populates="paper", uselist=False, cascade="all, delete-orphan")
    scores = relationship("PaperScore", back_populates="paper", uselist=False, cascade="all, delete-orphan")


class PaperAnalysis(Base):
    __tablename__ = "paper_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis = Column(Text, nullable=True)
    model = Column(String(50), nullable=True)
    status = Column(String(20), default="success", index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class PaperChat(Base):
    __tablename__ = "paper_chats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PaperSimilarity(Base):
    __tablename__ = "paper_similarities"
    __table_args__ = (
        UniqueConstraint("paper_id_a", "paper_id_b", name="uq_paper_similarities_pair"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id_a = Column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    paper_id_b = Column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    similarity_score = Column(Float, nullable=False)
    computed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PaperFeatures(Base):
    __tablename__ = "paper_features"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), unique=True, nullable=False)
    summary = Column(Text, nullable=True)
    keywords = Column(UnicodeJSON, default=list)
    embedding = Column(String, nullable=True)
    topic = Column(String(50), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    paper = relationship("Paper", back_populates="features")


class PaperScore(Base):
    __tablename__ = "paper_scores"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), unique=True, nullable=False)
    recency_score = Column(Float, default=0.0)
    venue_score = Column(Float, default=0.0)
    trend_score = Column(Float, default=0.0)
    final_score = Column(Float, default=0.0, index=True)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    paper = relationship("Paper", back_populates="scores")


class TopicTrend(Base):
    __tablename__ = "topic_trends"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    topic = Column(String(50), nullable=False, index=True)
    week_start = Column(DateTime, nullable=False, index=True)
    paper_count = Column(Integer, default=0)
    growth_rate = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CrawlLog(Base):
    __tablename__ = "crawl_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    journal_name = Column(String(200), nullable=False, index=True)
    crawl_start_time = Column(DateTime, nullable=False, index=True)
    crawl_end_time = Column(DateTime, nullable=True)
    papers_fetched = Column(Integer, default=0)
    papers_failed = Column(Integer, default=0)
    status = Column(String(20), nullable=False, default="running", index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TrendChat(Base):
    __tablename__ = "trend_chats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("ai_analysis_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class AIAnalysisReport(Base):
    __tablename__ = "ai_analysis_reports"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    summary = Column(Text, nullable=True)
    hot_topics = Column(UnicodeJSON, nullable=True)
    development_trends = Column(UnicodeJSON, nullable=True)
    keyword_insights = Column(UnicodeJSON, nullable=True)
    journal_insights = Column(UnicodeJSON, nullable=True)
    recommendations = Column(UnicodeJSON, nullable=True)
    raw_analysis = Column(Text, nullable=True)
    model = Column(String(50), nullable=True)
    total_papers = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    processing_time_ms = Column(Integer, default=0)
    status = Column(String(20), default="success")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ResearchGapReport(Base):
    """研究空白 LLM 解读报告（P1）。

    多用户预留：user_id 当前恒为 "local"，接入账号体系后按真实用户隔离，
    表结构无需迁移。
    """
    __tablename__ = "research_gap_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    gaps_snapshot = Column(UnicodeJSON, nullable=True)  # 触发时的空白组合快照（数据可追溯）
    raw_analysis = Column(Text, nullable=True)          # LLM 生成的空白假设卡片（markdown）
    model = Column(String(50), nullable=True)
    status = Column(String(20), default="running", index=True)
    error_message = Column(Text, nullable=True)
    processing_time_ms = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TopicProject(Base):
    """选题工作台：把「验证过的选题」沉淀为可决策、可跟踪的项目（P6）。

    多用户预留：user_id 当前恒为 "local"，接入账号体系后按真实用户隔离。
    status 流转：to_validate -> validated -> subscribed -> abandoned，
    用于记录选题从「刚验证」到「决定做了(订阅跟踪)」或「放弃」的决策状态。
    """
    __tablename__ = "topic_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    title = Column(String(500), nullable=False)            # 选题标题
    source_gap = Column(String(200), nullable=True)        # 来源空白词对，如 "耐心资本×新质生产力"
    source_paper_id = Column(Integer, nullable=True)       # 若从某篇论文起题，记录来源论文 id
    validation_report = Column(Text, nullable=True)        # 验证器生成的报告（markdown）
    novelty = Column(Integer, nullable=True)               # 新颖性评分 1-10
    crowding = Column(String(20), nullable=True)           # 拥挤度 低/中/高
    feasibility = Column(Integer, nullable=True)           # 可行性评分 1-10
    status = Column(String(20), default="to_validate", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Favorite(Base):
    """收藏（P1-10 个人化）：替代 localStorage，跨设备可用。

    多用户预留：user_id 当前恒为 "local"。
    """
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "paper_id", name="uq_favorites_user_paper"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    paper_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PinnedPaper(Base):
    """手动置顶（P2 置顶改造）：用户主动置顶的论文在列表中始终排最前。

    P1-10 之前"置顶"是 by 分数的自动徽章（语义误导）；本项目改为真正的
    用户手动置顶：本表只存用户主动置顶的 paper_id，排序时置顶优先。
    多用户预留：user_id 当前恒为 "local"，与收藏/阅读历史一致。
    """

    __tablename__ = "pinned_papers"
    __table_args__ = (
        UniqueConstraint("user_id", "paper_id", name="uq_pinned_user_paper"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    paper_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# 手动置顶上限：置顶超过该数量时不再新增置顶（前端据此提示）。
# 与列表置顶置序查询的 limit 保持一致，避免"置顶了却不排最前"的静默问题。
MAX_PINNED_PAPERS = 100


class HiddenPreference(Base):
    """不感兴趣/内容屏蔽（P2）：用户声明不想看的领域/期刊/关键词/作者。

    命中（任一）屏蔽项（如 subfield 含某领域，或 keywords 含某关键词）的论文，
    将从各论文列表（首页/搜索/工作台等）中被过滤，全局生效。
    entity_type ∈ {subfield, journal, keyword, author}；多用户预留 user_id 恒 "local"。
    """

    __tablename__ = "hidden_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "entity_value", name="uq_hidden_user_type_value"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    entity_type = Column(String(32), nullable=False)  # subfield | journal | keyword | author
    entity_value = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReadingHistory(Base):
    """阅读历史（P1-10 个人化）：已读/未读标记与"我的研究栈"数据源。"""
    __tablename__ = "reading_history"
    __table_args__ = (
        UniqueConstraint("user_id", "paper_id", name="uq_reading_user_paper"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    paper_id = Column(String(36), nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), server_default=func.now())


class FollowedSubfield(Base):
    """关注的子领域（P1-10 个人化）：驱动研究工作台推荐与领域快讯。"""
    __tablename__ = "followed_subfields"
    __table_args__ = (
        UniqueConstraint("user_id", "subfield", name="uq_followed_user_subfield"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    subfield = Column(String(100), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReviewReport(Base):
    """综述生成报告（P2-11 产出环节）：输入选题 -> 检索论文 -> AI 结构化综述。

    多用户预留：user_id 当前恒为 "local"。
    """
    __tablename__ = "review_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    topic = Column(String(500), nullable=False)          # 综述选题
    content = Column(Text, nullable=True)                # markdown 综述正文
    papers_json = Column(UnicodeJSON, nullable=True)     # 引用的论文列表快照
    model = Column(String(50), nullable=True)
    status = Column(String(20), default="running", index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BatchReport(Base):
    """批量分析报告（P1-8 异步化）：多选论文 -> 后台任务生成领域综述摘要。

    #7 遗留改造：原同步长请求改为后台任务 + 轮询，前端不再长时间阻塞转圈。
    """
    __tablename__ = "batch_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    paper_ids_json = Column(UnicodeJSON, nullable=True)   # 参与分析的论文 id 列表
    paper_count = Column(Integer, default=0)
    content = Column(Text, nullable=True)                 # markdown 综述摘要
    model = Column(String(50), nullable=True)
    status = Column(String(20), default="running", index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
