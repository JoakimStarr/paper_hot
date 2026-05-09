# 知网期刊爬虫增量更新计划

## 目标

实现增量式爬虫，支持断点续传和历史记录复用，避免重复爬取已获取的数据。

## 数据文件结构

### 1. 期刊历史记录 (backend/journals\_history.json)

```json
{
  "last_updated": "2025-01-15T10:30:00",
  "journals": {
    "期刊名称": {
      "url": "期刊链接",
      "last_crawled": "最后爬取时间"
    }
  }
}
```

### 2. 论文链接历史记录 (backend/papers\_history.json)

```json
{
  "last_updated": "2025-01-15T10:30:00",
  "papers": {
    "期刊名称": {
      "2026": {
        "03": {
          "last_crawled": "最后爬取时间",
          "papers": [
            {"title": "论文标题", "url": "论文链接", "status": 0}
          ]
        }
      }
    }
  }
}
```

### 3. 论文详情历史记录 (backend/paper\_details\_history.json)

```json
{
  "last_updated": "2025-01-15T10:30:00",
  "details": {
    "论文链接": {
      "status": 1,
      "crawled_at": "爬取时间",
      "data": {论文详情数据}
    }
  }
}
```

## 实现步骤

### 步骤1: 期刊链接获取与复用

1. 启动时检查 `journals_history.json` 是否存在
2. 如果存在且未过期（如7天内），直接加载使用
3. 如果不存在或已过期：

   * 访问知网期刊导航页

   * 点击"经济与管理科学"按钮

   * 获取div.result中的期刊列表

   * 立即保存到 `journals_history.json`

### 步骤2: 论文链接获取与复用

对于每个期刊：

1. 检查 `papers_history.json` 中是否已有该期刊指定年份（2025-2026）的数据
2. 如果存在且包含所有期次的数据，直接复用
3. 如果不存在或不完整：

   * 访问期刊页面

   * 获取YearIssueTree中的年份期次

   * 点击每个期次，获取论文列表

   * 点击span#larrow获取前一期，直到禁用

   * 立即保存到 `papers_history.json`

### 步骤3: 论文详情获取与状态管理

对于每篇论文：

1. 检查状态：

   * status=1（已获取）：跳过

   * status=0（未获取）：继续获取
2. 获取论文详情：

   * 访问论文页面

   * 提取标题、作者、摘要、关键词

   * 提取DOI、专辑、专题、分类号、在线公开时间
3. 更新状态：

   * 将status设置为1

   * 记录crawled\_at时间

   * 立即保存到 `paper_details_history.json`
4. 异步写入数据库

### 步骤4: 数据库操作

* 使用异步方式写入数据库

* 数据库表结构保持不变

* 写入前检查是否已存在（避免重复）

## 代码结构修改

### 新增类和方法

```python
class HistoryManager:
    """历史记录管理器"""
    
    def load_journals_history(self) -> dict:
        """加载期刊历史记录"""
        
    def save_journals_history(self, journals: dict):
        """保存期刊历史记录"""
        
    def load_papers_history(self) -> dict:
        """加载论文链接历史记录"""
        
    def save_papers_history(self, papers: dict):
        """保存论文链接历史记录"""
        
    def load_details_history(self) -> dict:
        """加载论文详情历史记录"""
        
    def save_details_history(self, details: dict):
        """保存论文详情历史记录"""
        
    def is_journal_crawled(self, journal_name: str, year: str) -> bool:
        """检查期刊某年份是否已爬取"""
        
    def is_paper_crawled(self, paper_url: str) -> bool:
        """检查论文是否已获取详情"""
        
    def update_paper_status(self, paper_url: str, status: int, data: dict = None):
        """更新论文获取状态"""

class IncrementalCrawler:
    """增量爬虫主类"""
    
    async def crawl_journals(self) -> dict:
        """获取期刊列表（带缓存）"""
        
    async def crawl_papers_for_journal(self, journal_name: str, journal_url: str, years: list) -> dict:
        """获取期刊论文链接（带缓存）"""
        
    async def crawl_paper_detail(self, paper_info: dict) -> dict:
        """获取论文详情（带状态检查）"""
        
    async def save_to_database(self, paper_data: dict):
        """异步保存到数据库"""
```

## 执行流程

```
开始
  ↓
检查期刊历史记录
  ↓
存在且有效？ → 是 → 加载期刊列表
  ↓ 否
爬取期刊列表
  ↓
保存期刊历史记录
  ↓
遍历每个期刊
  ↓
检查论文链接历史记录（该期刊指定年份）
  ↓
存在且完整？ → 是 → 加载论文链接
  ↓ 否
爬取论文链接
  ↓
保存论文链接历史记录
  ↓
遍历每篇论文
  ↓
检查详情状态
  ↓
status=1？ → 是 → 跳过
  ↓ 否
爬取论文详情
  ↓
更新状态为1
  ↓
保存详情历史记录
  ↓
异步写入数据库
  ↓
结束
```

## 参数配置

```python
# 配置常量
TARGET_YEARS = ['2025', '2026']  # 目标年份
JOURNAL_CACHE_DAYS = 7  # 期刊缓存有效期（天）
PAPER_CACHE_DAYS = 30  # 论文链接缓存有效期（天）
```

## 注意事项

1. 每次获取数据后立即保存，确保断点续传
2. 使用异步方式写入数据库，不阻塞爬取流程
3. 状态标记：0=未获取，1=已获取
4. 支持手动重置状态（将status改回0可重新获取）

