"""受信期刊集合与检索去噪工具。

背景：库内 CNKI 论文经由关键词检索路径混入了大量不在经济学 TOP50 名单内的
无关期刊（如中国瓜菜、北方果树、现代园艺、体育学刊等），会让 AI 检索/引用把
低质论文混进结果。这里维护「受信期刊」白名单，供 agent 工具、选题验证召回、
综述检索统一去噪：

- CNKI 经济学 TOP50（与 fetchers_cnki 配置一致。注意 fetchers_cnki 顶部 import
  DrissionPage 等重依赖，轻量服务器不能 import 它，故此处静态维护名单）
- 库内高频出现的正经经管期刊补充（不在 TOP50 名单但学术性可靠）
- arxiv 源论文始终受信

用法：
    from app.journal_filter import filter_trusted_papers
    papers = filter_trusted_papers(papers, journal_field="journal_name")
过滤后为空时默认保留原结果（保证功能不因过滤而中断）。
"""
from typing import Iterable, List, Optional

# CNKI 经济学 TOP50（与 backend/app/fetchers_cnki.py 的 CNKI_TOP50_JOURNALS 保持一致）
CNKI_TOP50_JOURNALS = {
    "经济研究", "管理世界", "经济学（季刊）", "世界经济", "中国工业经济",
    "中国社会科学", "金融研究", "数量经济技术经济研究", "财贸经济", "中国农村经济",
    "经济学动态", "国际经济评论", "改革", "中国人口科学", "农业经济问题",
    "中国农村观察", "财政研究", "税务研究", "会计研究", "审计研究",
    "国际贸易问题", "国际经贸探索", "世界经济研究", "经济社会体制比较", "经济学家",
    "经济科学", "经济理论与经济管理", "南开经济研究", "当代经济科学", "当代经济研究",
    "财经科学", "财经问题研究", "上海经济研究", "经济纵横", "经济问题探索",
    "经济问题", "经济经纬", "经济评论", "经济导刊", "经济研究参考",
    "经济研究导刊", "经济师", "经济界", "经济视角", "经济论坛",
    "经济工作导刊", "经济师论坛", "经济学家论坛", "经济学消息报",
}

# 补充受信期刊：不在 TOP50 名单但库内常见、学术性可靠的经管期刊
EXTRA_TRUSTED_JOURNALS = {
    "南开管理评论", "经济管理", "财经研究", "证券市场导报", "中南财经政法大学学报",
    "产业经济研究", "外国经济与管理", "经济与管理研究", "统计与决策", "财会月刊",
    "金融监管研究", "国际金融研究", "投资研究", "统计研究", "中国管理科学",
    "管理科学", "管理学报", "管理评论", "中国软科学", "科研管理",
    "科学学研究", "农业技术经济", "农村金融研究", "中央财经大学学报", "山西财经大学学报",
    "首都经济贸易大学学报", "现代经济探讨", "经济体制改革", "国际贸易", "金融经济学研究",
    "管理现代化", "会计研究",
}

# arxiv / 自建站点来源视为受信（源级别白名单，匹配 papers.source）
TRUSTED_SOURCES = {"arxiv"}

TRUSTED_JOURNALS = CNKI_TOP50_JOURNALS | EXTRA_TRUSTED_JOURNALS


def is_trusted_journal(journal_name: Optional[str]) -> bool:
    """期刊名是否在受信白名单（归一化全/半角括号）。"""
    if not journal_name:
        return False
    name = journal_name.strip().replace("（", "(").replace("）", ")")
    return name in TRUSTED_JOURNALS


def is_trusted_source(source: Optional[str]) -> bool:
    return (source or "").strip().lower() in TRUSTED_SOURCES


def filter_trusted_papers(
    papers: Iterable[dict],
    journal_field: str = "journal_name",
    source_field: str = "source",
) -> List[dict]:
    """按受信期刊过滤论文列表；过滤后为空则保留原结果（兜底不中断功能）。

    - journal_name 命中受信白名单，或
    - source 命中受信来源（如 arxiv）
    的论文保留；其余丢弃。
    """
    papers = list(papers)
    if not papers:
        return papers
    kept = [
        p for p in papers
        if is_trusted_journal(p.get(journal_field)) or is_trusted_source(p.get(source_field))
    ]
    return kept if kept else papers
