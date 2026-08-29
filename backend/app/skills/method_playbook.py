"""方法手册技能（econometrics-skills 三元组模式）：方法 = 适用场景 + 数据需求 + 假设 + 诊断清单 + 参考实现。

注入路径：data_insights 生成时按选题标题/检索关键词匹配条目，
- matched_methods（ids）随 data_insights JSON 落库，前端 GET /skills/method-playbook 渲染完整卡片；
- 命中条目的摘要同时注入 LLM prompt，让 methods 建议与手册对齐。
条目为系统预置的静态文本（Script 侧），不是 LLM 生成物。
"""
import re
from typing import Dict, List

NAME = "method_playbook"
DESCRIPTION = "经管研究方法手册：设计/数据/假设/诊断/参考实现 三元组条目 + 关键词匹配"

# 关键词匹配的规范化：小写、去空白
_WORD_RE = re.compile(r"[\s，,、]+")


def _match_text(text: str) -> str:
    return (text or "").lower()


# ---- 预置方法条目（每条 = 适用场景 / 数据需求 / 关键假设 / 必做诊断 / 参考实现） ----
PLAYBOOK: List[Dict] = [
    {
        "id": "did",
        "name": "多期双重差分（Staggered DID）",
        "aliases": ["双重差分", "did", "政策冲击", "试点", "准自然实验"],
        "applies": "政策或冲击在不同时间作用于不同个体/地区，需要评估政策的因果效应",
        "data_needs": "个体×时间面板；处理组与处理时点标识；结果变量与协变量",
        "assumptions": "平行趋势（处理前趋势平行）；无预期效应；处理效应异质时需稳健估计量",
        "diagnostics": [
            "平行趋势检验（事件研究图，处理前系数应不显著）",
            "Placebo 政策时点检验",
            "异质性处理效应稳健估计（Callaway–Sant'Anna csdid / Sun–Abraham）",
            "处理组与控制组协变量平衡性检验",
        ],
        "code_hint": "Stata: csdid y, ivar(id) time(t) gvar(g), agg(event)；Python: linearmodels.PanelOLS + 事件研究虚拟变量",
    },
    {
        "id": "psm_did",
        "name": "PSM-DID（倾向得分匹配 + 双重差分）",
        "aliases": ["psm", "倾向得分", "匹配", "psm-did"],
        "applies": "处理组与控制组特征差异大，先用匹配构造可比样本再做 DID",
        "data_needs": "处理前多个协变量（用于匹配）；面板结果变量",
        "assumptions": "条件独立（协变量覆盖选择机制）；共同支撑域；匹配后仍满足平行趋势",
        "diagnostics": [
            "匹配后协变量平衡性检验（标准化偏差 <10%）",
            "共同支撑域与重叠图",
            "1:1 / 核匹配 / 卡尺匹配的稳健性对比",
            "匹配后样本的平行趋势检验",
        ],
        "code_hint": "Stata: psmatch2 + reghdfe；Python: causalinference / psmpy + linearmodels",
    },
    {
        "id": "iv",
        "name": "工具变量法（IV / 2SLS）",
        "aliases": ["工具变量", "iv", "2sls", "内生性"],
        "applies": "核心解释变量内生（反向因果/遗漏变量），存在外生工具时",
        "data_needs": "结果变量、内生解释变量、工具变量、协变量（截面或面板）",
        "assumptions": "工具相关性（强工具）；排他性约束（仅通过内生变量影响结果）；单调性",
        "diagnostics": [
            "第一阶段 F 统计量（弱工具检验，Kleibergen-Paap rk Wald F > 10）",
            "过度识别检验（Hansen J，需多个工具）",
            "工具外生性讨论（历史/地理/制度工具的制度论证）",
            "LIML / 不同工具集组合的稳健性",
        ],
        "code_hint": "Stata: ivregress 2sls y (x = z) controls, robust；Python: linearmodels.IV2SLS",
    },
    {
        "id": "rdd",
        "name": "断点回归（RDD）",
        "aliases": ["断点", "rdd", "门槛", "临界值"],
        "applies": "处理由连续-running-variable 的临界值决定（分数线/规模阈值/年龄线）",
        "data_needs": "驱动变量（连续）、结果变量、断点两侧足够密集的观测",
        "assumptions": "断点处个体不能精确操纵驱动变量；局部随机化；带宽内协变量平衡",
        "diagnostics": [
            "McCrary 密度连续性检验（操纵检验）",
            "协变量在断点处的连续性检验",
            "不同带宽与多项式阶数的稳健性（稳健带宽选择）",
            "Placebo 断点检验",
        ],
        "code_hint": "Stata: rdrobust y x, c(cutoff)；Python: rdd / rdrobust 包",
    },
    {
        "id": "panel_fe",
        "name": "面板固定效应（Two-way FE）",
        "aliases": ["固定效应", "面板", "fe", "双向固定效应", "个体效应"],
        "applies": "控制不随时间变化的个体异质性与共同时间趋势的基准因果/相关分析",
        "data_needs": "个体×时间面板；核心解释变量随时间变化（组内变异）",
        "assumptions": "严格外生性（给定 FE 的条件下）；处理变量组内存在变异；无严重测量误差",
        "diagnostics": [
            "Hausman 检验（FE vs RE）",
            "组内变异诊断（解释变量时变比例过低则 FE 识别力弱）",
            "聚类稳健标准误（个体层面）",
            "剔除极端年份/个体的稳健性",
        ],
        "code_hint": "Stata: reghdfe y x controls, absorb(id year) vce(cluster id)；Python: linearmodels.PanelOLS(entity_effects=True, time_effects=True)",
    },
    {
        "id": "event_study",
        "name": "事件研究法（Event Study）",
        "aliases": ["事件研究", "event study", "公告效应", "市场反应"],
        "applies": "某一事件（政策公告/并购/上市）前后的动态效应刻画",
        "data_needs": "事件日标识；面板或高频截面；事件窗口内观测",
        "assumptions": "事件外生或可预期性可控；窗口内无混杂事件",
        "diagnostics": [
            "事件前系数（预期效应/趋势预存检验）",
            "事件窗口长度与累积效应的稳健性",
            "控制同期宏观冲击（时间固定效应）",
            "异常值与极端收益的处理",
        ],
        "code_hint": "Stata: reghdfe y i.rel_time, absorb(id event_date)；Python: 手工相对时间虚拟变量 + PanelOLS",
    },
    {
        "id": "synthetic_control",
        "name": "合成控制法（Synthetic Control）",
        "aliases": ["合成控制", "synthetic", "scm", "单一处理对象"],
        "applies": "处理单元极少（一个省/一个城市），需要构造加权反事实",
        "data_needs": "处理单元 + 池化对照单元的较长时间序列；处理前预测变量",
        "assumptions": "处理前拟合良好；对照单元未受处理外溢；无重大同期混杂",
        "diagnostics": [
            "处理前拟合优度（RMSPE）",
            "Placebo 循环（把处理施加于对照单元）与排序推断",
            "对照单元外溢敏感性",
            "不同预测变量组合的稳健性",
        ],
        "code_hint": "Stata: synth / sdid；Python: SyntheticControlMethods / pysynthcontrol",
    },
    {
        "id": "text_analysis",
        "name": "文本分析与词典法",
        "aliases": ["文本分析", "词典", "情感", "年报文本", "nlp", "语调"],
        "applies": "从年报/公告/新闻等文本构造测度（情绪/可读性/主题/披露质量）",
        "data_needs": "结构化文本语料（年报 MD&A、公告、新闻）；文本与个体的映射",
        "assumptions": "词典/模型测度的构造效度；文本代表性；测度不与遗漏变量同源",
        "diagnostics": [
            "测度与既有基准的相关性（如 L&M 词典对比）",
            "人工标注子样本的效度校验",
            "停用词/分词方案的敏感性",
            "测度的时序与截面合理性（分布、相关性方向）",
        ],
        "code_hint": "Python: jieba 分词 + 自建词典；进阶：sklearn TfidfVectorizer / 预训练语言模型嵌入",
    },
    {
        "id": "ml_prediction",
        "name": "机器学习预测与异质性（ML in Economics）",
        "aliases": ["机器学习", "预测", "ml", "随机森林", "lgbm", "异质性"],
        "applies": "预测任务、变量筛选、异质性处理效应发现（非因果主识别）",
        "data_needs": "大样本特征工程数据；训练/验证/测试划分",
        "assumptions": "样本外分布稳定；特征无泄漏；因果解释需结合因果方法",
        "diagnostics": [
            "时间外推验证（按时间切分而非随机切分）",
            "特征重要性 + SHAP 解释",
            "与基准线性模型的对比（增量预测力）",
            "超参数与随机种子的稳健性",
        ],
        "code_hint": "Python: lightgbm / sklearn + shap；Stata: 少用，建议 Python 侧完成",
    },
    {
        "id": "spatial",
        "name": "空间计量（Spatial Econometrics）",
        "aliases": ["空间", "spatial", "空间溢出", "地理加权"],
        "applies": "结果存在地理/网络空间相关（溢出效应、集聚、邻居效应）",
        "data_needs": "地理/邻接/经济距离权重矩阵；空间单元面板或截面",
        "assumptions": "权重矩阵设定合理（外生或稳健性替换）；空间自相关结构正确",
        "diagnostics": [
            "Moran's I 空间自相关检验",
            "LM 检验选择 SAR/SEM/SAC 设定",
            "权重矩阵替换（邻接/距离/经济权重）的稳健性",
            "直接/间接（溢出）效应分解",
        ],
        "code_hint": "Stata: spmat + spregress；Python: libpysal + spreg",
    },
]

_BY_ID: Dict[str, Dict] = {e["id"]: e for e in PLAYBOOK}

_REQUIRED_KEYS = ("id", "name", "aliases", "applies", "data_needs", "assumptions", "diagnostics", "code_hint")


def match_methods(text: str) -> List[Dict]:
    """按关键词匹配方法条目（大小写不敏感；别名含中文方法名与英文缩写）。"""
    t = _match_text(text)
    if not t:
        return []
    hits = []
    for entry in PLAYBOOK:
        for alias in entry["aliases"]:
            if alias.lower() in t:
                hits.append(entry)
                break
    return hits


def match_project(title: str, keywords: List[str] = ()) -> List[Dict]:
    """按项目标题 + 检索关键词匹配（Step1 的 search_keywords / 灵感快照 keywords）。"""
    blob = " ".join([title or ""] + [k for k in (keywords or []) if k])
    return match_methods(blob)


def entries_by_ids(ids: List[str]) -> List[Dict]:
    return [_BY_ID[i] for i in (ids or []) if i in _BY_ID]


def to_prompt_block(entries: List[Dict]) -> str:
    """命中条目 -> 注入 LLM 的摘要块（诱导 methods 建议与手册对齐）。"""
    if not entries:
        return ""
    lines = ["【系统预置方法手册（命中条目摘要；若与选题相关，请在 methods 中纳入并在 note 引用条目名）】"]
    for e in entries:
        lines.append(
            f"- {e['name']}：适用={e['applies']}；数据={e['data_needs']}；"
            f"关键假设={e['assumptions']}"
        )
    return "\n".join(lines)
