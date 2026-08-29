"""技能层（第二期）：把散落在各 router 的 AI prompt 收敛为自包含、可测试的技能模块。

设计（移植自 academic-paper / literature-review / paper-audit / econometrics-skills 四个技能的模式）：
- 每个技能 = prompt 模板 + 输入契约 + 输出 schema + 降级路径；
- 技能只负责「构造 prompt」与「解析输出」，不持有 LLM 客户端（调用方注入），
  因此纯函数、可单测；
- [Script]/[LLM] 证据分离：确定性统计由后端预计算后以「Script 证据」注入，
  与模型判断显式区分（paper-audit 模式）；
- 盲态预承诺：评分标准由系统固定写死（而非看过证据的模型临时生成），
  模型只能按标准归档打分，并在结论中引用所落档位（academic-paper 生成器-评估器契约）。

注册表见 registry.py。
"""
