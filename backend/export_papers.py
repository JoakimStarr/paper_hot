#!/usr/bin/env python3
import sqlite3
import json
import re
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from pathlib import Path

DB_PATH = "/home/joakim/Project/paper_hot/backend/data/paperpulse.db"
OUTPUT_DIR = Path("/home/joakim/Project/hmAPP/blog/source/paper/data")


def datetime_to_str(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def export_papers(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            p.id, p.title, p.abstract, p.authors, p.keywords_cn, p.doi,
            p.journal_name, p.journal_issue, p.source, p.venue, p.published_at,
            p.url, p.discipline, p.economics_subfield, p.cnki_subject,
            ps.recency_score, ps.venue_score, ps.trend_score, ps.final_score,
            pf.topic, pf.summary
        FROM papers p
        LEFT JOIN paper_scores ps ON p.id = ps.paper_id
        LEFT JOIN paper_features pf ON p.id = pf.paper_id
        ORDER BY ps.final_score DESC
    """)
    
    papers = []
    for row in cursor.fetchall():
        paper = {
            "id": row[0],
            "title": row[1],
            "abstract": row[2],
            "authors": json.loads(row[3]) if row[3] else [],
            "keywords_cn": json.loads(row[4]) if row[4] else [],
            "doi": row[5],
            "journal_name": row[6],
            "journal_issue": row[7],
            "source": row[8],
            "venue": row[9],
            "published_at": datetime_to_str(row[10]),
            "url": row[11],
            "discipline": row[12],
            "economics_subfield": row[13],
            "cnki_subject": row[14],
            "recency_score": row[15] or 0.0,
            "venue_score": row[16] or 0.0,
            "trend_score": row[17] or 0.0,
            "final_score": row[18] or 0.0,
            "topic": row[19],
            "summary": row[20]
        }
        papers.append(paper)
    
    output_path = OUTPUT_DIR / "papers.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)
    
    print(f"导出 papers.json: {len(papers)} 条记录")
    return papers


def export_meta(conn, papers):
    journals = Counter()
    disciplines = Counter()
    subfields = Counter()
    cnki_subjects = Counter()
    sources = Counter()
    topics = Counter()
    
    for paper in papers:
        if paper.get("journal_name"):
            journals[paper["journal_name"]] += 1
        if paper.get("discipline"):
            disciplines[paper["discipline"]] += 1
        if paper.get("economics_subfield"):
            subfields[paper["economics_subfield"]] += 1
        if paper.get("cnki_subject"):
            for part in paper["cnki_subject"].split(";"):
                part = part.strip()
                if part:
                    cnki_subjects[part] += 1
        if paper.get("source"):
            sources[paper["source"]] += 1
        if paper.get("topic"):
            topics[paper["topic"]] += 1
    
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM papers")
    total_papers = cursor.fetchone()[0]
    
    cursor.execute("SELECT MIN(published_at), MAX(published_at) FROM papers WHERE published_at IS NOT NULL")
    date_range = cursor.fetchone()
    
    cursor.execute("SELECT AVG(final_score), MAX(final_score), MIN(final_score) FROM paper_scores")
    score_stats = cursor.fetchone()
    
    meta = {
        "total_papers": total_papers,
        "exported_at": datetime.now().isoformat(),
        "date_range": {
            "start": datetime_to_str(date_range[0]),
            "end": datetime_to_str(date_range[1])
        },
        "score_stats": {
            "average": round(score_stats[0] or 0, 4),
            "max": round(score_stats[1] or 0, 4),
            "min": round(score_stats[2] or 0, 4)
        },
        "journals": [{"name": k, "count": v} for k, v in journals.most_common(50)],
        "disciplines": [{"name": k, "count": v} for k, v in disciplines.most_common()],
        "subfields": [{"name": k, "count": v} for k, v in subfields.most_common()],
        "cnki_subjects": [{"name": k, "count": v} for k, v in cnki_subjects.most_common(50)],
        "sources": [{"name": k, "count": v} for k, v in sources.most_common()],
        "topics": [{"name": k, "count": v} for k, v in topics.most_common()]
    }
    
    output_path = OUTPUT_DIR / "papers.meta.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    
    print(f"导出 papers.meta.json: 元数据统计")
    return meta


def export_similarities(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            ps.paper_id_a, ps.paper_id_b, ps.similarity_score,
            pa.title as title_a, pb.title as title_b,
            pfa.topic as topic_a, pfb.topic as topic_b,
            pa.keywords_cn as kw_a, pb.keywords_cn as kw_b
        FROM paper_similarities ps
        JOIN papers pa ON ps.paper_id_a = pa.id
        JOIN papers pb ON ps.paper_id_b = pb.id
        LEFT JOIN paper_features pfa ON ps.paper_id_a = pfa.paper_id
        LEFT JOIN paper_features pfb ON ps.paper_id_b = pfb.paper_id
        ORDER BY ps.paper_id_a, ps.similarity_score DESC
    """)
    
    paper_similarities = defaultdict(list)
    for row in cursor.fetchall():
        paper_id_a = row[0]
        paper_id_b = row[1]
        similarity_score = row[2]
        
        paper_similarities[paper_id_a].append({
            "id": paper_id_b,
            "title": row[4],
            "similarity_score": round(similarity_score, 4),
            "topic": row[6],
            "keywords_cn": json.loads(row[8]) if row[8] else []
        })
    
    similarities = {}
    for paper_id, similar_papers in paper_similarities.items():
        similarities[paper_id] = similar_papers[:5]
    
    output_path = OUTPUT_DIR / "similarities.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(similarities, f, ensure_ascii=False, indent=2)
    
    print(f"导出 similarities.json: {len(similarities)} 篇论文的相似数据")
    return similarities


def is_valid_author_name(name):
    if not name or not isinstance(name, str):
        return False
    name = name.strip()
    if len(name) < 2:
        return False
    if re.match(r'^[\s\[\]",\.\-\d\(\)\{\}]+$', name):
        return False
    if not re.search(r'[\u4e00-\u9fff]', name):
        return False
    return True

def is_valid_keyword(keyword):
    if not keyword or not isinstance(keyword, str):
        return False
    keyword = keyword.strip()
    if len(keyword) < 2:
        return False
    if re.match(r'^[\s\[\]",\.\-\d\(\)\{\}]+$', keyword):
        return False
    if not re.search(r'[\u4e00-\u9fff]', keyword):
        return False
    return True

def export_author_network(papers):
    author_papers = defaultdict(list)
    author_coauthors = defaultdict(lambda: defaultdict(int))
    
    for paper in papers:
        authors = paper.get("authors", [])
        if not authors:
            continue
        
        valid_authors = [a.strip() for a in authors if is_valid_author_name(a)]
        
        for author in valid_authors:
            author_papers[author].append(paper["id"])
        
        for i, author_a in enumerate(valid_authors):
            for author_b in valid_authors[i+1:]:
                pair = tuple(sorted([author_a, author_b]))
                author_coauthors[pair[0]][pair[1]] += 1
                author_coauthors[pair[1]][pair[0]] += 1
    
    top_authors = sorted(author_papers.keys(), key=lambda x: len(author_papers[x]), reverse=True)[:50]
    
    nodes = []
    for author in top_authors:
        nodes.append({
            "id": author,
            "name": author,
            "paper_count": len(author_papers[author])
        })
    
    edges = []
    author_set = set(top_authors)
    edge_set = set()
    
    for author_a in top_authors:
        for author_b, weight in author_coauthors[author_a].items():
            if author_b in author_set:
                edge_key = tuple(sorted([author_a, author_b]))
                if edge_key not in edge_set:
                    edges.append({
                        "source": author_a,
                        "target": author_b,
                        "weight": weight
                    })
                    edge_set.add(edge_key)
    
    network = {
        "nodes": nodes,
        "edges": edges
    }
    
    output_path = OUTPUT_DIR / "network.authors.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(network, f, ensure_ascii=False, indent=2)
    
    print(f"导出 network.authors.json: {len(nodes)} 个节点, {len(edges)} 条边")
    return network


def export_keyword_network(papers):
    keyword_papers = defaultdict(list)
    keyword_cooccur = defaultdict(lambda: defaultdict(int))
    
    for paper in papers:
        keywords = paper.get("keywords_cn", [])
        if not keywords:
            continue
        
        valid_keywords = [k.strip() for k in keywords if is_valid_keyword(k)]
        
        for keyword in valid_keywords:
            keyword_papers[keyword].append(paper["id"])
        
        for i, kw_a in enumerate(valid_keywords):
            for kw_b in valid_keywords[i+1:]:
                pair = tuple(sorted([kw_a, kw_b]))
                keyword_cooccur[pair[0]][pair[1]] += 1
                keyword_cooccur[pair[1]][pair[0]] += 1
    
    top_keywords = sorted(keyword_papers.keys(), key=lambda x: len(keyword_papers[x]), reverse=True)[:200]
    
    nodes = []
    for keyword in top_keywords:
        nodes.append({
            "id": keyword,
            "name": keyword,
            "paper_count": len(keyword_papers[keyword])
        })
    
    edges = []
    keyword_set = set(top_keywords)
    edge_set = set()
    
    for kw_a in top_keywords:
        for kw_b, weight in keyword_cooccur[kw_a].items():
            if kw_b in keyword_set:
                edge_key = tuple(sorted([kw_a, kw_b]))
                if edge_key not in edge_set:
                    edges.append({
                        "source": kw_a,
                        "target": kw_b,
                        "weight": weight
                    })
                    edge_set.add(edge_key)
    
    network = {
        "nodes": nodes,
        "edges": edges
    }
    
    output_path = OUTPUT_DIR / "network.keywords.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(network, f, ensure_ascii=False, indent=2)
    
    print(f"导出 network.keywords.json: {len(nodes)} 个节点, {len(edges)} 条边")
    return network


def export_trends(conn):
    cursor = conn.cursor()
    
    now = datetime.now()
    trends = {}
    
    for period_name, days_back in [("1month", 30), ("3months", 90), ("6months", 180)]:
        cutoff_date = now - timedelta(days=days_back)
        
        cursor.execute("""
            SELECT topic, SUM(paper_count) as total_count, AVG(growth_rate) as avg_growth
            FROM topic_trends
            WHERE week_start >= ?
            GROUP BY topic
            ORDER BY avg_growth DESC
            LIMIT 20
        """, (cutoff_date.isoformat(),))
        
        hot_topics = []
        for row in cursor.fetchall():
            hot_topics.append({
                "topic": row[0],
                "paper_count": row[1],
                "growth_rate": round(row[2], 4) if row[2] else 0
            })
        
        trends[period_name] = {
            "period": period_name,
            "days_back": days_back,
            "hot_topics": hot_topics
        }
    
    cursor.execute("""
        SELECT topic, week_start, paper_count, growth_rate
        FROM topic_trends
        ORDER BY topic, week_start
    """)
    
    topic_timeline = defaultdict(list)
    for row in cursor.fetchall():
        topic_timeline[row[0]].append({
            "date": datetime_to_str(row[1]),
            "count": row[2],
            "growth_rate": round(row[3], 4) if row[3] else 0
        })
    
    trends["timeline"] = dict(topic_timeline)
    
    output_path = OUTPUT_DIR / "trends.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(trends, f, ensure_ascii=False, indent=2)
    
    print(f"导出 trends.json: 趋势数据")
    return trends


def export_subfield_distribution(papers):
    subfield_scores = defaultdict(list)
    
    for paper in papers:
        subfield = paper.get("economics_subfield")
        if subfield:
            subfield_scores[subfield].append(paper.get("final_score", 0))
    
    distribution = []
    for subfield, scores in subfield_scores.items():
        avg_score = sum(scores) / len(scores) if scores else 0
        distribution.append({
            "subfield": subfield,
            "paper_count": len(scores),
            "avg_score": round(avg_score, 4),
            "max_score": round(max(scores), 4) if scores else 0,
            "min_score": round(min(scores), 4) if scores else 0
        })
    
    distribution.sort(key=lambda x: x["paper_count"], reverse=True)
    
    output_path = OUTPUT_DIR / "subfield.distribution.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(distribution, f, ensure_ascii=False, indent=2)
    
    print(f"导出 subfield.distribution.json: {len(distribution)} 个子领域")
    return distribution


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 50)
    print("开始导出论文数据...")
    print(f"数据库: {DB_PATH}")
    print(f"输出目录: {OUTPUT_DIR}")
    print("=" * 50)
    
    conn = sqlite3.connect(DB_PATH)
    
    try:
        papers = export_papers(conn)
        export_meta(conn, papers)
        export_similarities(conn)
        export_author_network(papers)
        export_keyword_network(papers)
        export_trends(conn)
        export_subfield_distribution(papers)
        
        print("=" * 50)
        print("导出完成!")
        print("=" * 50)
        
        output_files = list(OUTPUT_DIR.glob("*.json"))
        print(f"\n导出文件列表:")
        for f in sorted(output_files):
            size_kb = f.stat().st_size / 1024
            print(f"  - {f.name}: {size_kb:.2f} KB")
        
    finally:
        conn.close()


if __name__ == "__main__":
    main()
