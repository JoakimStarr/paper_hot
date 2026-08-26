# 遗留问题清单（2026-08-26 复核后）

> 对照 PRODUCT_PLAN.md 逐项实施后的真实状态。已完成项已标注 ✅，
> 仅保留「仍未彻底关闭」的项及其处置结论。验证基线：后端 pytest 45 passed、前端 tsc --noEmit 通过。

---

## 一、数据层（P0）

### 1. 经济学季刊摘要/卷期 —— 决定"刻意不做"（影响极小）
- 根因：`fetchers.py` `JingjixueJikanFetcher` 卷期 viid 硬编码且易失效，返回空列表；
  摘要需经 CNKI AbstractUrl 单独抓取（依赖浏览器会话/Cookie）。
- 处置结论：库内该刊仅 **2 篇**且均有摘要，修复需引入"浏览器端抓取 + 登录态"链路，
  对个人工具成本/维护收益严重失衡。**刻意不修，记为已知边界**。后续若扩充该刊，
  应统一走 `scheduler.backfill_abstracts` 的浏览器抓取路径，而非单独重写本爬虫。

### 2. ✅ 存量 embedding 自动补齐
- 已实现 `crud.get_papers_missing_embeddings` + `scheduler.backfill_embeddings_incremental`，
  服务启动时自动增量补齐（只处理 `embedding IS NULL`，不重建既有向量），batch_size ≤20。

### 3. ✅ topic_trends 陈旧 / 趋势近窗为空
- `scheduler.update_trends` 已挂入 `start.sh dev` 启动流程，启动即刷新趋势，
  `GET /trending-topics?weeks_back=8` 不再返回空。

---

## 二、功能层（已完成项）

### 4. ✅ Dashboard「领域快讯」AI 一句话结论
- `routers/dashboard.py _briefing` 已接通 `_briefing_ai_note`（1h TTL 缓存，AI 不可用降级 None）。

### 5. ✅ 阅读历史"已读"视觉标记
- PaperCard 已加载 read_ids，已读论文标题置灰。

### 6. ✅ 真 docx 导出
- `lib/utils.ts downloadAsWord` 已用 docx 库生成真 .docx。

### 7. ✅ 批量分析异步化
- `POST /papers/batch-analyze` → 后台任务 + `BatchReport` 轮询，前端不再长时间转圈。

### 8. ✅ producer 综述用户隔离
- ReviewReport 写入按 `x-user-id` 头隔离（默认 local）。

### 9. ✅ keyword-map / producer 检索性能
- 关键词过滤与召回下推到 SQL（json_each / 库内过滤），不再 Python 侧全表扫描。

---

## 三、工程债

### 10. ⚠️ i18n 部分完成
- ✅ layout `<html lang>` 已改为随已保存语言首帧生效（内联合法脚本读 localStorage）。
- 知识库已建立完整 zh/en 词表（home/trends/topics/system/network/paper/filters 主流程均已走 `useLanguage().t`）。
- 未尽项：dashboard / ProducerLab / 网络图研究版图 / TrendChart 等**本次新增页面的部分按钮文案**仍是硬编码中文，
  英文模式下中英混合。属纯文案打磨，改动面大、价值低，列为待办（个人单用户工具，非闭环阻断项）。

### 11. ✅ 系统管理页拆分
- system/page.tsx 已拆分为多子组件。

### 12. ⚠️ 验证码自动识别 —— 已集成守卫式方案，待真机验证
- `fetchers_cnki.py` `DrissionPageBase.handle_captcha` 已并入 ddddocr 滑块自动解决：
  - `import ddddocr` 失败（服务端未装）时自动降级为人工处理，不影响主流程；
  - 新增 `backend/requirements-crawler.txt`（原 requirements.txt 注释指向但文件缺失），
    爬虫 + 验证码依赖在此统一声明。
- 未尽项：CNKI 滑块选择器/滑动像素换算基于通用经验值，**需在真实 CNKI 页面跑通后微调**
  （当前 try/except 兜底，失败即转人工，不会中断爬取）。

### 13. ✅ D3 缩放位置丢失 / @types/mermaid@9 与运行时 v11 错位
- zoom transform 用 ref 保存，主题切换后恢复；已移除过时 @types/mermaid。

---

## 四、测试缺口

### 14. ✅ 新增端点自动化测试补齐
- `tests/test_new_endpoint_helpers.py` 覆盖 `_rule_relevance_score` / `_aggregate_research_map` / `_crowding_stats`。
- 现有 pytest 45 passed。

---

## 五、P3 明确未做（计划内后续，非缺陷）

- 数据源扩展：CSSCI、Crossref/OpenAlex 接入
- 多用户 + 团队协作（选题库共享）
- 新论文订阅推送（每日邮件/接口）

---

## 快速验证备忘

```bash
# 后端测试
cd backend && ../../.venv/Scripts/python.exe -m pytest tests/ -q
# 前端类型检查
cd frontend && npx tsc --noEmit
# 冒烟（服务启动后）
curl "localhost:8000/api/dashboard"
curl "localhost:8000/api/papers?search=%22数字%22%20NOT%20社会"
curl "localhost:8000/api/network/keyword-map?keyword=数字经济"
```