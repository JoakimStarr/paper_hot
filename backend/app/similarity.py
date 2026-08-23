import jieba
import logging
from typing import List, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> str:
    if not text:
        return ""
    return " ".join(jieba.cut(text))


def compute_all_similarities(papers: List[Tuple[str, str]]) -> List[Tuple[str, str, float]]:
    if len(papers) < 2:
        return []

    ids = [p[0] for p in papers]
    abstracts = [p[1] or "" for p in papers]

    vectorizer = TfidfVectorizer(
        tokenizer=lambda x: x.split(),
        token_pattern=None,
        max_features=10000,
    )
    tokenized = [_tokenize(a) for a in abstracts]
    tfidf_matrix = vectorizer.fit_transform(tokenized)

    sim_matrix = cosine_similarity(tfidf_matrix)

    # 阈值过低会产生近百万条记录；按篇保留 Top-N 更符合"相似推荐"用途
    threshold = 0.1
    top_n_per_paper = 20
    n = len(ids)
    results = []
    for i in range(n):
        candidates = []
        row = sim_matrix[i]
        for j in range(n):
            if j == i:
                continue
            score = float(row[j])
            if score > threshold:
                candidates.append((j, score))
        candidates.sort(key=lambda x: x[1], reverse=True)
        for j, score in candidates[:top_n_per_paper]:
            a, b = (i, j) if i < j else (j, i)
            results.append((ids[a], ids[b], score))

    # 同一对可能从两端各保留一次，按 (a, b) 去重取高分
    seen: dict = {}
    for a, b, score in results:
        key = (a, b)
        if key not in seen or score > seen[key]:
            seen[key] = score
    return [(a, b, s) for (a, b), s in seen.items()]


async def compute_and_store_for_paper(db, paper_id: str):
    from sqlalchemy import select
    from app.models import Paper, PaperSimilarity
    from app.crud import PaperSimilarityCRUD

    paper = await db.execute(
        select(Paper).where(Paper.id == paper_id)
    )
    paper = paper.scalar_one_or_none()
    if not paper:
        return

    all_result = await db.execute(
        select(Paper.id, Paper.abstract).where(Paper.id != paper_id)
    )
    others = all_result.all()
    if not others:
        return

    papers = [(paper.id, paper.abstract)] + [(r[0], r[1]) for r in others]
    results = compute_all_similarities(papers)

    await PaperSimilarityCRUD.delete_by_paper(db, paper_id)

    for id_a, id_b, score in results:
        if paper_id not in (id_a, id_b):
            continue
        sim = PaperSimilarity(paper_id_a=id_a, paper_id_b=id_b, similarity_score=score)
        db.add(sim)

    await db.flush()
    logger.info(f"Computed similarities for paper {paper_id}: {len(results)} pairs stored")