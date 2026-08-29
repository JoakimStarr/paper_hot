"""站点结构常量 + 纯解析函数（无浏览器依赖，可独立测试）。

收录：知网站点常量、检索字段全集、参考文献条目解析（年份/来源/题名判重键）。
"""
import re

# —— 知网站点常量 ——
BASE_URL = 'https://navi.cnki.net'
VERIFY_URL_PREFIX = 'https://kns.cnki.net/verify/'
TARGET_YEARS = ['2025', '2026']

# —— 检索字段全集（取值即知网站点字段名，前端下拉与 --search-field 均基于此，见 demo.py）——
CNKI_SEARCH_FIELDS = [
    "主题", "篇关摘", "关键词", "篇名", "全文", "作者", "第一作者", "通讯作者",
    "作者单位", "基金", "摘要", "小标题", "参考文献", "分类号", "文献来源", "DOI",
]

# 检索字段 → 侧边栏筛选分组(div#divGroup 中 dl@dt@groupitem) 的映射：
# 命中分组时，在该分组内按关键词匹配最恰当的一项并点选，进一步收窄结果。
# 无映射的字段（篇关摘/篇名/关键词/全文/摘要/小标题/参考文献/DOI）不做分组筛选。
# 注意：检索字段「文献来源」对应侧边栏分组「文献来源」(WXLY)，不是「期刊」(QK)。
SEARCH_FIELD_GROUP_MAP = {
    "主题": "主题",
    "作者": "作者",
    "第一作者": "作者",
    "通讯作者": "作者",
    "作者单位": "机构",
    "基金": "基金",
    "文献来源": "文献来源",
    "分类号": "学科",
}

# —— 参考文献条目解析（参考文献详情入库用）——
# 知网参考文献页签里的条目是它自己的引文格式（作者在后）：
#   「[1] 数据要素成为中国经济增长新动能的机制探析[J]. 刘涛雄;张亚迪.经济研究,2024(10)」
# GB/T 7714 格式（作者在前）同样兼容：「1. 张三. 中国经济增长研究[J]. 经济研究, 2020(3): 12-25.」
# 知网详情页不直接给出发表年份：缺年份入库会落到「今年」，而综合分里 recency 权重 0.35
# （180 天半衰期），一批老文献就会伪装成新论文霸占发现流——解析不到年份的条目宁可跳过。
REF_TYPE_MARK_RE = re.compile(r'\[[A-Z]{1,2}(?:/[A-Z]{2})?\]')
# 年份区间：1920s 起的古典文献（如凯恩斯 1936）也要能解析，太老的上限统一封在 2059
REF_YEAR_RE = re.compile(r'(?<!\d)(19[2-9]\d|20[0-5]\d)(?!\d)')
# 可直接导航的知网详情页：新版 kcms2/article/abstract 与旧版 kcms/detail/detail.aspx
CNKI_DETAIL_URL_RE = re.compile(r'^https?://[^/]*cnki\.net/.*(?:kcms|detail)', re.I)


def _norm_title(title: str) -> str:
    """标题归一化：去掉空白与标点，只留字符数字，用于跨入口判重。"""
    return re.sub(r'[\s\W_]+', '', title or '')


def _is_cnki_detail_url(url) -> bool:
    """是否是可直接导航的知网详情页链接（参考文献列表里还有图书/外文等无链接条目）。"""
    return bool(url) and bool(CNKI_DETAIL_URL_RE.match(url))


def _parse_ref_meta(text: str) -> tuple:
    """从参考文献条目原文兜底 (年份, 文献来源)；解析不到对应字段时为 None。

    年份取第一个形似年份的数字；文献来源取「紧挨年份之前、最后一个句点之后」的片段——
    期刊名/学位授予单位都落在这个位置，且对不带类型标记（[J] 等）的条目同样有效；
    图书的「出版地: 出版社」带冒号、作者列表带分隔符（;，等），一律不认作来源。
    """
    text = text or ''
    m = REF_TYPE_MARK_RE.search(text)
    tail = text[m.end():] if m else text
    year_m = REF_YEAR_RE.search(tail)
    if not year_m:
        return None, None
    # 中英文分隔不一致：中文「.期刊名,2024(10)」、英文「.Journal Name.2024」，
    # 先吃掉年份前的尾部分隔符，再取最后一个句点之后的片段
    seg = re.sub(r'[.。，,；;：:\s]+$', '', tail[:year_m.start()])
    seg = re.split(r'[.。]', seg)[-1]
    seg = re.sub(r'[,，:：;；\s]+$', '', seg).strip()
    if not seg or any(ch in seg for ch in ',，;；、:：'):
        journal = None
    else:
        journal = seg[:40]
    return int(year_m.group(1)), journal


def _ref_title_keys(text: str) -> set:
    """从参考文献条目原文抽题名的候选归一化 key，用于「本地已有则不打开详情页」的判重。

    题名在文献类型标记（如 [J]）之前，去掉开头序号即得到；作者在前著录时（GB/T 7714）
    再补一个「去掉作者段」的候选。抽不到返回空集合，判重自然不命中——只会多打开一次
    详情页，不会误判成已有。
    """
    text = text or ''
    m = REF_TYPE_MARK_RE.search(text)
    if m:
        head = text[:m.start()]
    else:
        # 无类型标记的条目（如「[1] 题名. 作者.期刊,2026(06)」）：题名在第一个句点之前
        head = re.split(r'[.。]', text)[0]
    if not head:
        return set()
    head = re.sub(r'^\s*[\[【]?\d+[\]】]?\s*[.、．]?\s*', '', head)
    keys = {head, re.split(r'[.。]\s*', head)[-1]}
    return {k for k in (_norm_title(x) for x in keys) if k}
