export function getIssuePeriod(doi: string | null, publishedAt: string | null, journalIssue: string | null): string {
  if (journalIssue) return journalIssue;
  if (doi) {
    const fy = doi.match(/f\.(\d{4})\.(\d+)$/);
    if (fy && fy[2].length === 4) {
      const issue = Math.min(Math.ceil(parseInt(fy[2], 10) / 5), 12);
      return `${fy[1]}年 第${issue}期`;
    }
    const mm = doi.match(/\.(\d{4})\.(\d{2})\.(\d+)$/);
    if (mm) {
      return `${mm[1]}年 第${parseInt(mm[2], 10)}期`;
    }
    const ymd = doi.match(/\.(\d{4})(\d{2})(\d{2})\.(\d+)$/);
    if (ymd) {
      return `${ymd[1]}年 第${parseInt(ymd[2], 10)}期`;
    }
  }
  if (publishedAt) {
    return `${new Date(publishedAt).getFullYear()}年`;
  }
  return '';
}

export const topicColors: Record<string, string> = {
  LLM: 'bg-purple-100 text-purple-800',
  Agent: 'bg-green-100 text-green-800',
  CV: 'bg-blue-100 text-blue-800',
  RL: 'bg-orange-100 text-orange-800',
  Multimodal: 'bg-pink-100 text-pink-800',
  NLP: 'bg-yellow-100 text-yellow-800',
  Generative: 'bg-indigo-100 text-indigo-800',
  Other: 'bg-gray-100 text-gray-800',
};