export type Language = 'zh' | 'en';

export interface Translations {
  [key: string]: string | Translations;
}

export const translations = {
  zh: {
    // 通用
    appName: 'PaperPulse',
    appDescription: '发现和理解热门研究论文',
    
    // 导航
    nav: {
      home: '首页',
      trends: '趋势分析',
      system: '系统管理',
    },
    
    // 首页
    home: {
      title: '发现热门研究论文',
      subtitle: '及时了解来自各大期刊的最新论文',
      showingPapers: '显示 {start}-{end} 共 {total} 篇论文',
      noPapers: '未找到符合条件的论文',
      loadMore: '加载更多',
      previous: '上一页',
      next: '下一页',
    },
    
    // 筛选器
    filters: {
      title: '筛选条件',
      topic: '主题',
      allTopics: '全部主题',
      source: '来源',
      allSources: '全部来源',
      minScore: '最低分数',
      anyScore: '任意分数',
      discipline: '学科领域',
      allDisciplines: '全部学科',
      ai: '人工智能',
      economics: '经济学',
      economicsSubfield: '经济学子领域',
      allSubfields: '全部子领域',
      macroeconomics: '宏观经济学',
      microeconomics: '微观经济学',
      econometrics: '计量经济学',
      financialEconomics: '金融经济学',
      industrialEconomics: '产业经济学',
      developmentEconomics: '发展经济学',
      internationalEconomics: '国际经济学',
      journal: '期刊',
      allJournals: '全部期刊',
      activeFilters: '当前筛选：',
      clearAll: '清除全部',
    },
    
    // 论文卡片
    paper: {
      top: '置顶',
      trending: '热门',
      score: '评分',
      readMore: '阅读更多',
      journal: '期刊',
      issue: '期号',
      publishedAt: '发表时间',
      authors: '作者',
      abstract: '摘要',
      summary: '摘要总结',
      keywords: '关键词',
      similarPapers: '相似论文',
      shouldReadScore: '推荐阅读评分',
      highlyRecommended: '强烈推荐！该论文来自顶级期刊且正在热门趋势中。',
      worthReading: '值得一读。该论文在多个指标上表现良好。',
      considerReading: '如果与您的研究兴趣相关，可以考虑阅读。',
    },
    
    // 趋势页面
    trends: {
      title: '主题趋势',
      subtitle: '追踪哪些研究主题正在获得关注',
      paperCount: '论文数量',
      growthRate: '增长率',
      rising: '上升',
      stable: '稳定',
      declining: '下降',
    },
    
    // 系统管理页面
    system: {
      title: '系统管理',
      subtitle: '管理系统爬取任务和日志',
      crawlControl: '爬取控制',
      crawlLogs: '爬取日志',
      startCrawl: '启动爬取',
      selectJournals: '选择期刊',
      crawling: '正在爬取...',
      crawlStatus: '爬取状态',
      logTime: '时间',
      logJournal: '期刊',
      logStatus: '状态',
      logPapers: '论文数',
      logDetails: '详情',
    },
    
    // 页脚
    footer: {
      description: '发现热门研究论文平台',
      builtWith: '使用 FastAPI 和 Next.js 构建',
    },
    
    // 语言切换
    language: {
      select: '选择语言',
      zh: '中文',
      en: 'English',
    },
  },
  
  en: {
    // General
    appName: 'PaperPulse',
    appDescription: 'Discover and understand trending research papers',
    
    // Navigation
    nav: {
      home: 'Home',
      trends: 'Trends',
      system: 'System',
    },
    
    // Home
    home: {
      title: 'Discover Trending Research Papers',
      subtitle: 'Stay updated with the latest papers from top journals',
      showingPapers: 'Showing {start}-{end} of {total} papers',
      noPapers: 'No papers found matching your criteria',
      loadMore: 'Load More',
      previous: 'Previous',
      next: 'Next',
    },
    
    // Filters
    filters: {
      title: 'Filters',
      topic: 'Topic',
      allTopics: 'All Topics',
      source: 'Source',
      allSources: 'All Sources',
      minScore: 'Minimum Score',
      anyScore: 'Any Score',
      discipline: 'Discipline',
      allDisciplines: 'All Disciplines',
      ai: 'Artificial Intelligence',
      economics: 'Economics',
      economicsSubfield: 'Economics Subfield',
      allSubfields: 'All Subfields',
      macroeconomics: 'Macroeconomics',
      microeconomics: 'Microeconomics',
      econometrics: 'Econometrics',
      financialEconomics: 'Financial Economics',
      industrialEconomics: 'Industrial Economics',
      developmentEconomics: 'Development Economics',
      internationalEconomics: 'International Economics',
      journal: 'Journal',
      allJournals: 'All Journals',
      activeFilters: 'Active filters:',
      clearAll: 'Clear all',
    },
    
    // Paper Card
    paper: {
      top: 'Top',
      trending: 'Trending',
      score: 'Score',
      readMore: 'Read More',
      journal: 'Journal',
      issue: 'Issue',
      publishedAt: 'Published',
      authors: 'Authors',
      abstract: 'Abstract',
      summary: 'Summary',
      keywords: 'Keywords',
      similarPapers: 'Similar Papers',
      shouldReadScore: 'Should Read Score',
      highlyRecommended: 'Highly recommended! This paper is from a top venue and trending.',
      worthReading: 'Worth reading. This paper has good scores across multiple metrics.',
      considerReading: 'Consider if relevant to your specific research interests.',
    },
    
    // Trends Page
    trends: {
      title: 'Topic Trends',
      subtitle: 'Track which research topics are gaining momentum',
      paperCount: 'Paper Count',
      growthRate: 'Growth Rate',
      rising: 'Rising',
      stable: 'Stable',
      declining: 'Declining',
    },
    
    // System Page
    system: {
      title: 'System Management',
      subtitle: 'Manage system crawling tasks and logs',
      crawlControl: 'Crawl Control',
      crawlLogs: 'Crawl Logs',
      startCrawl: 'Start Crawl',
      selectJournals: 'Select Journals',
      crawling: 'Crawling...',
      crawlStatus: 'Crawl Status',
      logTime: 'Time',
      logJournal: 'Journal',
      logStatus: 'Status',
      logPapers: 'Papers',
      logDetails: 'Details',
    },
    
    // Footer
    footer: {
      description: 'Discover trending research papers platform',
      builtWith: 'Built with FastAPI and Next.js',
    },
    
    // Language
    language: {
      select: 'Select Language',
      zh: '中文',
      en: 'English',
    },
  },
};

export function getTranslation(lang: Language, key: string): string {
  const keys = key.split('.');
  let value: any = translations[lang];
  
  for (const k of keys) {
    if (value && typeof value === 'object' && k in value) {
      value = value[k];
    } else {
      return key; // 返回key作为fallback
    }
  }
  
  return typeof value === 'string' ? value : key;
}
