# 遗留问题清单（2026-08-25 重构实施后）

> 对照 PRODUCT_PLAN.md 逐项实施后的剩余缺口。已完成项不再列出，只记「还没做好」的。

---

## 一、数据层（P0 遗留）

### 1. 经济学季刊摘要仍会为空（根因未修）
- `fetchers.py:745`：`JingjixueJikanFetcher` 新爬论文仍是 `"abstract": ""`。
- 该刊走北大 ccj.pku.edu.cn API：卷期 viid 是硬编码（`fetchers.py:545-580` 注释自认"需要定期更新"，实测已失效返回空），摘要需经 CNKI AbstractUrl 单独抓取（依赖浏览器会话）。
- 现状影响小：库内仅 2 篇季刊论文且都有摘要。若后续扩充该刊，需重写其爬虫或接入 backfill_abstracts 的浏览器抓取路径。

### 2. 存量 embedding 未自动补齐
- scheduler 只保证**新入库**论文有 embedding；存量缺口仍需手动触发
  `POST /api/topic-validator/embeddings/backfill`（选题中心页面有按钮）。
- 可选改进：服务启动时检测 embedded/total < 1 自动跑一次增量补齐。

### 3. topic_trends 数据陈旧，趋势接口近窗返回空
- 实测 `topic_trends` 表最新 week_start = **2026-01-01**，导致
  `GET /trending-topics?weeks_back=8` 返回 0 条（weeks_back=52 才有 20 条）。
- weeks_back 参数本身已修好（papers.py:141），是**数据没更新**：update_trends 定时任务
  （每 6h）在当前环境未运行或未产生新周记录。部署环境确认 scheduler 开启即可；
  dashboard「领域快讯」同样受影响（取近 8 周窗口）。

---

## 二、功能层（P1/P2 打折项）

### 4. Dashboard「领域快讯」缺 AI 一句话结论
- 后端 `_briefing()` 恒返回 `ai_note: None`（dashboard.py:114），前端渲染逻辑已就位但永远不触发。
- 待补：LLM 从 Top5 趋势生成一句话结论（AI 不可用时保持纯数据降级，结构已支持）。

### 5. 阅读历史只有"上报"，没有"已读标记"展示
- 详情页会写 reading_history（P1-10b 已做），但列表页 PaperCard 没有"已读"视觉标记，
  plan 里"已读/未读标记"只完成了一半。可在 PaperCard 加载用户 read_ids 后置灰标题。

### 6. 综述 Word 导出是 HTML 伪 doc
- `lib/utils.ts downloadAsWord()` 用 HTML blob + `.doc` 扩展名，Word/WPS 能打开但不是真 docx。
- 要真 docx 需引入 docx 库或走 Pandoc（前端体积代价 / 服务端依赖）。

### 7. 批量分析为同步长请求
- `POST /papers/batch-analyze` 同步等 LLM 返回（上限 10 篇，max_tokens=3072），慢时前端只能转圈。
- 改进方向：仿照 producer/review 的后台任务 + 轮询模式。

### 8. producer 综述的用户隔离未接 x-user-id
- `producer.py:125` 写死 `ReviewReport(user_id="local")`，多浏览器/多人共用一个本地身份时历史综述混在一起。
- 其余 personal/dashboard 接口均已按 header 隔离，此处遗漏。

---

## 三、性能

### 9. keyword-map 全表扫描在 Python 侧过滤
- `network.py get_keyword_research_map` 拉 4000 篇逐篇匹配关键词。当前 3497 篇没问题，
  语料过万后会慢。可改 SQLite json_each 直接 SQL 过滤（参考 crud.py 作者查询的写法）。
- 同类问题：producer.py `_retrieve_papers` 拉 2000 篇内存打分。

---

## 四、工程债（PLAN 第五节未动项）

### 10. i18n 未完成（且本次新增了一批硬编码中文）
- `<html lang="zh">` 仍硬编码（layout.tsx:17）。
- topics/system/network 各页原有硬编码中文未清理；本次新增的 dashboard、ProducerLab、
  网络图研究版图、TrendChart 按钮等文案也是硬编码中文。英文模式下中英混合更严重了。

### 11. 系统管理页单文件过大
- system/page.tsx 仍 ~1500 行四 tab 混一文件，模型配置 tab 还塞着端口/API key，未拆分。

### 12. 爬虫稳定性：验证码自动识别未集成
- `_check_captcha` 依旧禁用状态，知网抓取依赖人工浏览器会话；
  cnki_paper_captcha.py 的 ddddocr 方案未并入主爬虫。

### 13. D3 图主题切换丢缩放位置、@types/mermaid@9 与运行时 v11 错位
- PLAN 技术债表原样未动。

---

## 五、测试缺口

### 14. 本次新增端点无自动化测试
- 现有 33 个测试全在纯函数层。以下新逻辑零覆盖：
  - `/papers/batch-analyze`（prompt 组装、截断到 10 篇）
  - `/papers/{id}/relevance`（规则兜底分支）
  - `/network/keyword-map`
  - `/trends/explain`
  - `/topic-validator/proposal`、`_competition_map`
  - `backfill_abstracts`（scheduler 任务）
  - 高级搜索解析器已有 test_advanced_search.py ✅（唯一例外）

---

## 六、P3 明确未做（计划内后续）

- 数据源扩展：CSSCI、Crossref/OpenAlex 接入
- 多用户 + 团队协作（选题库共享）
- 新论文订阅推送（每日邮件/接口）

---

## 快速验证备忘

```bash
# 后端测试
cd backend && ./venv/bin/python -m pytest tests/ -q
# 前端类型检查 + 构建
cd frontend && npx tsc --noEmit && npm run build
# 冒烟（服务启动后）
curl "localhost:8000/api/dashboard"
curl "localhost:8000/api/papers?search=%22数字%22%20NOT%20社会"
curl "localhost:8000/api/network/keyword-map?keyword=数字经济"
```
