/**
 * 验证报告评分解析（第一期轻量版）：
 * 从流式/已保存的验证报告 markdown 中提取新颖性评分与拥挤度，回填到项目字段，
 * 让列表卡的评分展示与状态流转不必等第二期的结构化输出改造。
 *
 * 匹配策略宽容（模型输出格式有波动）：
 * - 新颖性：/新颖性 ... N/（允许"评分/得分/："等连接词，允许 N/10、N分 形式），钳制到 1-10
 * - 拥挤度：/拥挤度 ... 低|中|高/
 */
export interface ParsedValidationScores {
  novelty?: number;
  crowding?: '低' | '中' | '高';
}

export function parseValidationScores(report: string): ParsedValidationScores {
  const out: ParsedValidationScores = {};

  const noveltyMatch = report.match(/新颖性[^\n\d]{0,12}(\d{1,2})\s*(?:\/\s*10|分)?/);
  if (noveltyMatch) {
    const n = parseInt(noveltyMatch[1], 10);
    if (n >= 1 && n <= 10) out.novelty = n;
  }

  const crowdingMatch = report.match(/拥挤度[^\n低中高]{0,8}(低|中|高)/);
  if (crowdingMatch) {
    out.crowding = crowdingMatch[1] as '低' | '中' | '高';
  }

  return out;
}
