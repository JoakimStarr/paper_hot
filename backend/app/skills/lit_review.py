"""文献综述技能：收敛 workbench（项目文献集）与 producer（全库检索）两套平行 prompt。

两处调用的差异只在输入侧（论文文本的来源与格式），综述的结构契约统一为本模块的
五个小节：研究脉络 / 方法演进 / 争议点 / 研究空白 / 可进一步研究。
"""
from typing import List, Optional

NAME = "lit_review"
DESCRIPTION = "结构化文献综述：研究脉络/方法演进/争议点/研究空白/可进一步研究（统一五节契约）"

SECTIONS = ("研究脉络", "方法演进", "争议点", "研究空白", "可进一步研究")


def build_messages(
    topic: str,
    papers_text: str,
    paper_count: Optional[int] = None,
    context_note: str = "项目文献集",
    max_tokens_note: bool = False,
) -> List[dict]:
    """构造综述 prompt。

    papers_text: 调用方自行格式化的编号论文文本（[n] 编号即引用编号）；
    context_note: 论文来源说明（「项目文献集」/「从论文库检索到」），
                  会写进 prompt，模型的措辞随之适配。
    """
    count_note = f"共 {paper_count} 篇，" if paper_count else ""
    system_prompt = f"""你是一位学术文献综述专家。请基于{context_note}的论文，为选题生成一份结构化文献综述。
选题：{topic}

{context_note}中的相关论文（{count_note}方括号为编号，按相关度排序）：
{papers_text}

请用 markdown 输出，包含以下五个小节（顺序固定）：
## 研究脉络
梳理该方向从早期到近期的研究演进，说明主线脉络与发展阶段。
## 方法演进
文献采用的研究方法从简单到复杂的演进路径（概念界定、计量方法、数据来源等）。
## 争议点
现有文献存在哪些分歧与争议（结论冲突、方法派别、测度差异等）。
## 研究空白
基于上述脉络，指出尚待填补的空隙——这正是新研究的切入机会。
## 可进一步研究
给出 2-3 个可行切入点。

要求：
1. 引用文献用 [编号] 标注（对应上方论文列表序号，从 1 开始），结论必须有文献支撑；
   检索/文献集未覆盖的内容要明确说明，禁止编造
2. 每个部分 2-4 段，结构清晰、观点明确"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请生成这份文献综述。"},
    ]
