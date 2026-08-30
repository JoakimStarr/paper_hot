"""技能注册表：名称 -> 自包含技能模块。

两层路由结构（econometrics-skills 模式）：本文件只是索引，每个技能的
prompt/契约/解析都在自己的模块里。调用方按需 import 技能模块或经 get_skill 取用。
"""
from typing import Dict, List, Optional

from app.skills import lit_review
from app.skills import method_playbook
from app.skills import validate
from app.skills import debate

SKILLS: Dict[str, object] = {
    validate.NAME: validate,
    method_playbook.NAME: method_playbook,
    lit_review.NAME: lit_review,
    debate.NAME: debate,
}


def get_skill(name: str):
    """按名称取技能模块；未注册返回 None。"""
    return SKILLS.get(name)


def list_skills() -> List[dict]:
    """技能清单（供 introspection / 调试端点）。"""
    return [{"name": s.NAME, "description": s.DESCRIPTION} for s in SKILLS.values()]
