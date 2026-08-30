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
    # 参考文献列表（JSON：[{index, text, url}]）——由参考文献爬取任务覆盖式写入，
    # 替代独立 paper_references 表（知网 URL 的 v 令牌随入口变化，随论文行存储更稳）
    references_cn = Column(UnicodeJSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    features = relationship("PaperFeatures", back_populates="paper", uselist=False, cascade="all, delete-orphan")
    scores = relationship("PaperScore", back_populates="paper", uselist=False, cascade="all, delete-orphan")


class PaperAnalysis(Base):
    __tablename__ = "paper_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    # 多用户预留：谁触发的分析。默认 "local"，与收藏/阅读历史等个人表一致。
    user_id = Column(String(50), default="local", index=True)
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
    # 任务类型（journal/keyword/cnki_top50/cnki_navi/arxiv 等）：前端「重跑」据此分发
    task_type = Column(String(20), nullable=False, default="journal", index=True)
    # 任务运行日志尾部（前端点开任务查看）；rerun_params 为重跑参数（JSON 字符串）
    log_detail = Column(Text, nullable=True)
    rerun_params = Column(Text, nullable=True)
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
    """研究工作台：把一个选题从「灵感 → 验证 → 文献 → 数据/方法 → 写作」沉淀为可跟踪的项目。

    多用户预留：user_id 当前恒为 "local"，接入账号体系后按真实用户隔离。
    status 流转：to_validate -> validated -> subscribed -> abandoned，
    用于记录选题从「刚验证」到「决定做了(订阅跟踪)」或「放弃」的决策状态。
    current_step 记录五步向导进度（1 选题定义 / 2 选题验证 / 3 文献管理 / 4 数据与方法 / 5 写作输出）；
    各步的 AI 产出（generated_topics/overview/data_insights/literature_review/proposal/journal_advice）
    均持久化在本表，ai_pending 标记正在执行的后台 AI 任务（供前端轮询）。
    """
    __tablename__ = "topic_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    title = Column(String(500), nullable=False)            # 选题标题
    source_gap = Column(String(200), nullable=True)        # 来源空白词对，如 "耐心资本×新质生产力"
    source_type = Column(String(20), default="manual")     # gap | keyword | idea | manual
    source_ref = Column(String(200), nullable=True)        # 来源引用（空白词对/热点词/一句话想法）
    source_paper_id = Column(Integer, nullable=True)       # 若从某篇论文起题，记录来源论文 id
    research_questions = Column(UnicodeJSON, nullable=True)  # 研究问题列表
    # 检索关键词：Step1 手动维护，驱动 Step2 验证检索与 Step3 文献召回；
    # 为空时前端回退到 generated_topics 快照里的 keywords
    search_keywords = Column(UnicodeJSON, nullable=True)
    validation_report = Column(Text, nullable=True)        # 验证器生成的报告（markdown）
    # 验证证据快照：{papers, mode, competition, validated_at}——召回列表/竞争地图随报告一起沉淀，
    # 否则重进验证步时只剩报告文本，证据（组件内存态）会丢
    validation_evidence = Column(UnicodeJSON, nullable=True)
    novelty = Column(Integer, nullable=True)               # 新颖性评分 1-10
    crowding = Column(String(20), nullable=True)           # 拥挤度 低/中/高
    feasibility = Column(Integer, nullable=True)           # 可行性评分 1-10
    gate = Column(String(20), nullable=True)               # 门控 pass/caution/avoid（验证/辩论/答辩裁决）
    verdict = Column(String(20), nullable=True)            # 答辩结论 通过/修改后通过/不通过
    current_step = Column(Integer, default=1)              # 五步向导进度 1-5
    generated_topics = Column(UnicodeJSON, nullable=True)  # Step1 LLM 生成的候选选题
    overview = Column(Text, nullable=True)                 # Step2 已有研究盘点（markdown）
    data_insights = Column(UnicodeJSON, nullable=True)     # Step4 数据/方法线索
    literature_review = Column(Text, nullable=True)        # Step3 文献脉络 / Step5 综述
    proposal = Column(Text, nullable=True)                 # 立项书
    journal_advice = Column(Text, nullable=True)           # 期刊适配结果
    # 辩论/答辩完整记录快照：{surface: debate|defense, rounds: [{id,label,model,text}],
    # scores: {novelty,crowding,feasibility,gate[,verdict]}, rounds_per_side, created_at}
    # —— 与 validation_evidence 同理：重进步骤时随项目一起恢复，组件内存态不丢
    debate_transcript = Column(UnicodeJSON, nullable=True)
    ai_pending = Column(String(50), nullable=True)         # 正在执行的后台 AI 任务名；空=空闲
    ai_error = Column(Text, nullable=True)                 # 最近一次 AI 任务错误信息（成功后清空）
    status = Column(String(20), default="to_validate", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProjectPaper(Base):
    """项目文献集：研究工作台某个项目里收集的相关论文（Step3 文献管理）。

    每条记录标记精读状态与笔记；similarity 为加入时与选题的相似度（embedding 召回值）。
    多用户预留：user_id 恒 "local"。
    """
    __tablename__ = "project_papers"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", "paper_id", name="uq_project_papers_user_project_paper"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    project_id = Column(Integer, nullable=False, index=True)
    paper_id = Column(String(36), nullable=False, index=True)
    similarity = Column(Float, nullable=True)              # 与选题的相似度（0-1）
    read_status = Column(String(20), default="to_read")    # to_read | reading | read
    note = Column(Text, nullable=True)                     # 用户笔记
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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


class FollowedKeyword(Base):
    """关注的关键词（P1-10 个人化）：驱动「今日值得读」关键词召回。"""
    __tablename__ = "followed_keywords"
    __table_args__ = (
        UniqueConstraint("user_id", "keyword", name="uq_followed_user_keyword"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    keyword = Column(String(100), nullable=False, index=True)
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


class SystemSetting(Base):
    """用户自定义配置持久化（设置页保存项，覆盖 .env/环境变量基线）。

    优先级：system_settings(DB) > 环境变量 > backend/.env。
    端口类键额外镜像写回 backend/.env：start.sh 在应用启动前读取端口。
    """
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AIFeedback(Base):
    """AI 回答的轻量反馈（👍/👎，P2）：为回答质量评估与提示词迭代积累信号。

    surface：trend_chat / paper_chat / validator / producer / gap；
    ref_id：report_id / paper_id 等上下文主键（可选）；rating：1 赞 / -1 踩。
    """
    __tablename__ = "ai_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    surface = Column(String(30), nullable=False, default="chat")
    ref_id = Column(String(100), nullable=True, index=True)
    content_hash = Column(String(64), nullable=True)     # 消息内容哈希，用于同一答案去重
    rating = Column(Integer, nullable=False)             # 1 或 -1
    model = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ActionLog(Base):
    """动作日志（日志系统）：中间件全量记录每个 API 请求，用于排查/审计。

    request_id 为单次请求的唯一标识，贯穿该请求的所有日志与错误记录。
    """
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(40), index=True)
    user_id = Column(String(100), index=True)
    method = Column(String(10))
    path = Column(String(300))
    status_code = Column(Integer)
    duration_ms = Column(Integer)
    query = Column(String(500), nullable=True)   # 请求查询串（截断；不存 body，防泄漏密钥）
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class ErrorLog(Base):
    """错误报告（日志系统）：后端未捕获异常 / 校验失败 / 前端上报统一入库。

    source：backend（后端异常）| frontend（前端上报）| scheduler（后台任务）。
    """
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(20), default="backend", index=True)
    request_id = Column(String(40), index=True)
    user_id = Column(String(100), index=True)
    method = Column(String(10), nullable=True)
    path = Column(String(300), nullable=True)
    status_code = Column(Integer, nullable=True)
    error_type = Column(String(100))
    error_message = Column(Text)
    traceback = Column(Text, nullable=True)
    request_info = Column(UnicodeJSON, nullable=True)   # 查询串/上下文详情（不含 body）
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class AssistantSession(Base):
    """全局 AI 悬浮助手会话（P2）：按页面上下文创建，保存历史记录。

    page/paper_id/context_text 记录会话起点上下文；消息存 assistant_messages 表。
    """
    __tablename__ = "assistant_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), index=True)
    title = Column(String(200), nullable=True)         # 由首条用户消息自动生成
    page = Column(String(30), default="generic")
    paper_id = Column(String(36), nullable=True)
    context_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class AssistantMessage(Base):
    """全局 AI 悬浮助手消息（P2）：属于某个 assistant_session。"""
    __tablename__ = "assistant_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, index=True)
    role = Column(String(20))                          # user | assistant
    content = Column(Text)
    reasoning = Column(Text, nullable=True)            # 助手消息的思考过程（reasoning_content），仅 assistant 有
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class UserEvent(Base):
    """用户行为埋点：追踪推荐曝光、点击、收藏等行为，用于量化推荐效果。

    event_type: impression(曝光) | click(点击) | favorite(收藏) | unfavorite(取消收藏)
    surface: dashboard_today_read | paper_list | search | ...
    ref_id: 关联的论文 ID（paper_id）
    meta: 扩展信息（如推荐分数、排名位置等 JSON）
    """
    __tablename__ = "user_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    event_type = Column(String(30), nullable=False, index=True)
    surface = Column(String(50), nullable=False, index=True)
    ref_id = Column(String(36), nullable=True, index=True)
    meta = Column(UnicodeJSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class PaperKeyword(Base):
    """论文关键词平表（工作台性能优化）：替代 json_each(p.keywords_cn) 全表扫描的关键词召回。

    keywords_cn 是 JSON 列，SQLite 无法对 json_each 展开建索引；本表一论文一关键词一行，
    keyword 列建索引后召回走索引查找。由回填脚本维护（见 scripts/backfill_paper_keywords.py，
    启动时空表自动后台回填），查询侧在表为空时自动回退 json_each，兼容未回填的库。
    paper_id 不设外键：与 Favorite/ProjectPaper 等个人表保持一致（论文被外部清理后由重建回填收敛）。
    """
    __tablename__ = "paper_keywords"
    __table_args__ = (
        UniqueConstraint("paper_id", "keyword", name="uq_paper_keywords_paper_kw"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String(36), nullable=False, index=True)
    keyword = Column(String(100), nullable=False, index=True)


class ReadLater(Base):
    """稍后读队列（工作台优化）：与收藏/置顶平行的轻量清单。

    与收藏（长期沉淀）区分：队列强调"待办"，看完一条就从队列移除并计入阅读历史。
    多用户预留：user_id 恒 "local"。
    """
    __tablename__ = "read_laters"
    __table_args__ = (
        UniqueConstraint("user_id", "paper_id", name="uq_read_later_user_paper"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="local", index=True)
    paper_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
