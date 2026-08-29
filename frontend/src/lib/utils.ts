export function getIssuePeriod(doi: string | null, publishedAt: string | null, journalIssue: string | null): string {
  // 未来年份兜底：CNKI「网络首发」文章常被编入超前卷期（如 2027 年第01期），
  // 此时 published_at / DOI 里都是未来年份，显示为具体未来年月会误导用户，
  // 统一标注为「网络首发」。
  const maskFuture = (s: string): string => {
    const m = s.match(/(20\d{2})/);
    if (m && parseInt(m[1], 10) > new Date().getFullYear()) return '网络首发';
    return s;
  };

  // 优先级 1: journal_issue（最准，CNKI 源为"2026年第03期"格式）
  if (journalIssue?.trim()) return maskFuture(journalIssue.trim());
  // 优先级 2: published_at（回退到"YYYY年M月"，比只显示年更有信息量）
  if (publishedAt) {
    const d = new Date(publishedAt);
    if (!Number.isNaN(d.getTime())) {
      return maskFuture(`${d.getFullYear()}年${d.getMonth() + 1}月`);
    }
  }
  // 优先级 3: DOI 启发式兜底（arXiv 等缺 issue 缺可靠日期时的最后一道）
  if (doi) {
    const fy = doi.match(/f\.(\d{4})\.(\d+)$/);
    if (fy && fy[2].length === 4) {
      const issue = Math.min(Math.ceil(parseInt(fy[2], 10) / 5), 12);
      return maskFuture(`${fy[1]}年 第${issue}期`);
    }
    const mm = doi.match(/\.(\d{4})\.(\d{2})\.(\d+)$/);
    if (mm) return maskFuture(`${mm[1]}年${parseInt(mm[2], 10)}月`);
    const ymd = doi.match(/\.(\d{4})(\d{2})(\d{2})\.(\d+)$/);
    if (ymd) return maskFuture(`${ymd[1]}年${parseInt(ymd[2], 10)}月`);
    const y4 = doi.match(/(19|20)\d{2}/);
    if (y4) return maskFuture(`${y4[0]}年`);
  }
  return '';
}

export const topicColors: Record<string, string> = {
  LLM: 'bg-purple-100 dark:bg-purple-900/40 text-purple-800 dark:text-purple-300',
  Agent: 'bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-300',
  CV: 'bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-300',
  RL: 'bg-orange-100 dark:bg-orange-900/40 text-orange-800 dark:text-orange-300',
  Multimodal: 'bg-pink-100 dark:bg-pink-900/40 text-pink-800 dark:text-pink-300',
  NLP: 'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-300',
  Generative: 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-800 dark:text-indigo-300',
};
/** 下载文本文件（Markdown / 引用 / BibTeX 等导出共用）。 */
export function downloadTextFile(filename: string, content: string, mime = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/** 导出 Word：动态加载 docx 库生成真正的 .docx 文件（仅在该函数被调用时按需加载，不增大首屏）。 */
export async function downloadAsWord(filename: string, title: string, markdownContent: string) {
  const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType } = await import('docx');

  // docx 经动态 import 引入，Paragraph 是值而非类型名，用 InstanceType 取其实例类型
  const paragraphs: InstanceType<typeof Paragraph>[] = [];

  // 文档首段：标题加粗、居中
  if (title.trim()) {
    paragraphs.push(
      new Paragraph({
        heading: HeadingLevel.TITLE,
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: title, bold: true })],
      }),
    );
  }

  const lines = markdownContent.split(/\r?\n/);
  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();

    if (trimmed === '') {
      paragraphs.push(new Paragraph({ spacing: { before: 160, after: 160 } }));
      continue;
    }

    // 标题行：为某个层级 如 # / ## / ###
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      const heading = level === 1 ? HeadingLevel.HEADING_1 : level === 2 ? HeadingLevel.HEADING_2 : HeadingLevel.HEADING_3;
      paragraphs.push(new Paragraph({ heading, children: [new TextRun(text)] }));
      continue;
    }

    // 无序列表
    if (/^[-*]\s+/.test(trimmed)) {
      paragraphs.push(new Paragraph({ children: [new TextRun(`• ${trimmed.replace(/^[-*]\s+/, '')}`)] }));
      continue;
    }

    // 其它正文
    paragraphs.push(new Paragraph({ children: [new TextRun(line)] }));
  }

  const doc = new Document({ sections: [{ children: paragraphs }] });
  const blob = await Packer.toBlob(doc);

  const baseName = filename.endsWith('.docx')
    ? filename
    : `${filename.replace(/\.(doc|docx)$/i, '')}.docx`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = baseName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const REFS_SHOW_BROWSER_KEY = 'paperpulse.refsShowBrowser';

/** 参考文献抓取是否显示浏览器（详情页与系统页-爬虫共用同一份偏好，localStorage 持久化） */
export function getRefsShowBrowser(): boolean {
  try {
    return typeof window !== 'undefined' && window.localStorage.getItem(REFS_SHOW_BROWSER_KEY) === '1';
  } catch {
    return false;
  }
}

export function rememberRefsShowBrowser(value: boolean): void {
  try {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(REFS_SHOW_BROWSER_KEY, value ? '1' : '0');
    }
  } catch { /* localStorage 不可用（隐私模式等）时静默 */ }
}
