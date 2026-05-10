# 论文相似度计算与持久化 Spec

## Why
当前相似论文仅靠 `features.topic` 粗分类匹配，大部分论文 topic 为 `"Other"`，返回结果实际不相似，`similarity_score` 硬编码为 `0.85`。需要基于摘要文本内容计算真实相似度，并持久化避免重复计算。

## What Changes
- 后端新增 `jieba` + `scikit-learn` 依赖用于中文分词和 TF-IDF 计算
- 新建 `paper_similarities` 表存储预计算的相似度
- 新增 `PaperSimilarityCRUD` 提供查询接口
- 修改 `get_similar_papers` 从表查询而非实时 topic 匹配
- 新增新论文入库后自动触发相似度计算的钩子
- 新增 `/api/papers/{paper_id}/recompute-similarities` 手动重算端点

## Impact
- Affected specs: 无（新功能）
- Affected code: `backend/app/crud.py`, `backend/app/models.py`, `backend/app/api.py`, `backend/requirements.txt`, `backend/app/database.py`（建表）

## ADDED Requirements

### Requirement: 论文摘要 TF-IDF 相似度计算
系统 SHALL 使用 jieba 中文分词 + scikit-learn TfidfVectorizer 计算论文摘要的余弦相似度。

#### Scenario: 新论文入库触发计算
- **WHEN** 新论文通过爬虫入库
- **THEN** 后台异步计算该论文与所有已有论文的相似度，写入 paper_similarities 表

#### Scenario: 手动重算某篇论文相似度
- **WHEN** 用户调用 `POST /api/papers/{paper_id}/recompute-similarities`
- **THEN** 删除该论文的旧相似度记录，重新计算并写入

#### Scenario: 全量重算
- **WHEN** 管理员调用全量重算
- **THEN** 清空 paper_similarities 表，对所有论文两两计算并写入

### Requirement: 相似度持久化存储
系统 SHALL 将预计算的相似度存储在 `paper_similarities` 表中。

#### Scenario: 查询某论文的相似论文
- **WHEN** 请求 `GET /api/papers/{paper_id}` 包含 similar_papers
- **THEN** 从 paper_similarities 表查询 similarity_score DESC TOP 5，返回真实相似度分数

#### Scenario: 无预计算数据
- **WHEN** 某论文尚无相似度记录
- **THEN** 返回空列表，并在响应中标记 `similarities_pending: true`

### Requirement: 相似论文响应格式
系统 SHALL 在 similar_papers 中返回真实的 similarity_score 和 keywords_cn。

#### Scenario: 返回相似论文
- **WHEN** 查询论文详情
- **THEN** similar_papers 中每项包含 id, title, similarity_score（0-1实数）, topic, keywords_cn

## MODIFIED Requirements

### Requirement: get_similar_papers 方法
**Before**: 按 `features.topic` 匹配 + 硬编码 0.85 分数
**After**: 查询 `paper_similarities` 表，按 `similarity_score DESC` 取 TOP 5

#### Scenario: 查询相似论文
- **WHEN** `PaperCRUD.get_similar_papers(db, paper_id, limit=5)` 被调用
- **THEN** 从 paper_similarities 表 JOIN papers 返回分数最高的论文，分数为真实余弦相似度