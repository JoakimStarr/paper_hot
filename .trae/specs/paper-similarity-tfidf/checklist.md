# Checklist

- [x] `jieba` 和 `scikit-learn` 已添加到 requirements.txt 并安装成功
- [x] `paper_similarities` 表存在于数据库，包含字段: id, paper_id_a, paper_id_b, similarity_score, computed_at
- [x] `paper_similarities` 表有 (paper_id_a, paper_id_b) 唯一约束，有 paper_id_a 和 paper_id_b 索引
- [x] `backend/app/similarity.py` 存在，包含 jieba 分词 + TF-IDF + 余弦相似度计算函数
- [x] `PaperSimilarityCRUD` 类存在于 crud.py，包含 get_similar_papers, get_similar_papers_with_scores, delete_by_paper, clear_all 方法
- [x] `PaperCRUD.get_similar_papers` 改为从 paper_similarities 表查询，不再使用 topic 匹配
- [x] `GET /api/papers/{paper_id}` 返回的 similar_papers 中 similarity_score 为真实计算值（非 0.85）
- [x] similar_papers 每项包含 keywords_cn 字段
- [x] `POST /api/papers/{paper_id}/recompute-similarities` 端点存在且可用
- [x] `POST /api/recompute-all-similarities` 端点存在且可用
- [x] 无预计算数据时 similar_papers 返回空列表（不报错）
- [x] 前端论文详情页相似论文展示正常，关键词和相似度分数正确显示
- [x] 后端正常启动，无导入错误