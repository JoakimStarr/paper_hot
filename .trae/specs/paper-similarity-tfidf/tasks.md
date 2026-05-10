# Tasks

- [x] Task 1: 安装依赖 — 在 `requirements.txt` 中添加 `jieba` 和 `scikit-learn`，并安装到当前环境
  - [x] 添加 jieba 和 scikit-learn 到 requirements.txt
  - [x] 执行 pip install 安装新依赖

- [x] Task 2: 建 paper_similarities 表
  - [x] 在 models.py 中添加 PaperSimilarity 模型
  - [x] 手动建表确保表存在
  - [x] 验证表结构正确（唯一索引 + 两列索引）

- [x] Task 3: 实现 TF-IDF 相似度计算模块
  - [x] 新建 `backend/app/similarity.py` — 封装 jieba 分词 + TfidfVectorizer + 余弦相似度
  - [x] 实现 `compute_all_similarities` 函数
  - [x] 实现 `compute_and_store_for_paper` 函数

- [x] Task 4: 新增 PaperSimilarityCRUD
  - [x] 在 crud.py 中新增 PaperSimilarityCRUD 类
  - [x] 实现 `get_similar_papers_with_scores` — 查表返回相似论文 + 分数映射
  - [x] 实现 `delete_by_paper` — 删除某论文的旧记录（含 flush）
  - [x] 实现 `clear_all` — 清空全表

- [x] Task 5: 修改 get_similar_papers 为查表模式
  - [x] 修改 PaperCRUD.get_similar_papers 调用 PaperSimilarityCRUD
  - [x] 确保返回的 Paper 对象包含 features 和 scores（selectinload）
  - [x] 更新 api.py 中 hardcode 的 0.85 为真实分数

- [x] Task 6: 手动重算端点 + 全量重算端点
  - [x] 在 api.py 添加 `POST /api/papers/{paper_id}/recompute-similarities` 端点
  - [x] 添加 `POST /api/recompute-all-similarities` 全量重算端点
  - [x] 从 PaperDetailResponse 移除 hardcode 的 0.85

- [x] Task 7: 验证与前端的兼容性
  - [x] 确认 similar_papers 响应格式不变（keywords_cn 保留）
  - [x] 确认 similarity_score 为真实分数（0-1 浮点数）
  - [x] 前端无需改动

- [x] Task 8: 重启服务并验证
  - [x] 执行 ./stop.sh && ./start.sh
  - [x] 验证后端正常启动
  - [x] 调用 recompute 端点触发计算
  - [x] 验证相似论文 API 返回真实分数

# Task Dependencies
- Task 2 依赖 Task 1（需要先确定 ORM 模型依赖就绪）
- Task 4 依赖 Task 2（CRUD 需要 PaperSimilarity 模型）
- Task 5 依赖 Task 4（查表需要 CRUD 方法）
- Task 6 依赖 Task 3, 4（计算需要 similarity 模块和 CRUD）
- Task 7 依赖 Task 5, 6
- Task 8 依赖 Task 7
- Task 1, 2, 3 可并行