import asyncio
import sys
sys.path.insert(0, '/home/joakim/Project/paper_hot/backend')

from datetime import datetime, timedelta
import random

from app.database import AsyncSessionLocal
from app.crud import PaperCRUD
from app.schemas import PaperCreate
from app.scoring import ScoringSystem

async def add_sample_papers():
    papers_data = [
        {
            "title": "Attention Is All You Need",
            "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.",
            "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit"],
            "url": "https://arxiv.org/abs/1706.03762",
            "source": "arxiv",
            "venue": "NeurIPS",
            "published_at": datetime.now() - timedelta(days=30)
        },
        {
            "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
            "abstract": "We introduce a new language representation model called BERT, which stands for Bidirectional Encoder Representations from Transformers. Unlike recent language representation models, BERT is designed to pre-train deep bidirectional representations from unlabeled text by jointly conditioning on both left and right context in all layers.",
            "authors": ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee", "Kristina Toutanova"],
            "url": "https://arxiv.org/abs/1810.04805",
            "source": "arxiv",
            "venue": "NAACL",
            "published_at": datetime.now() - timedelta(days=60)
        },
        {
            "title": "GPT-4 Technical Report",
            "abstract": "We report the development of GPT-4, a large-scale, multimodal model which can accept image and text inputs and produce text outputs. While less capable than humans in many real-world scenarios, GPT-4 exhibits human-level performance on various professional and academic benchmarks.",
            "authors": ["OpenAI"],
            "url": "https://arxiv.org/abs/2303.08774",
            "source": "arxiv",
            "venue": None,
            "published_at": datetime.now() - timedelta(days=5)
        },
        {
            "title": "Constitutional AI: Harmlessness from AI Feedback",
            "abstract": "As AI systems become more capable, we would like to enlist their help to supervise other AIs. We experiment with methods for training a harmless AI assistant through self-improvement, without any human labels identifying harmful outputs. The only human oversight is provided through a set of principles or rules.",
            "authors": ["Yuntao Bai", "Saurav Kadavath", "Sandeep Nair", "Andy Jones"],
            "url": "https://arxiv.org/abs/2212.08073",
            "source": "arxiv",
            "venue": None,
            "published_at": datetime.now() - timedelta(days=10)
        },
        {
            "title": "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models",
            "abstract": "We explore how generating a chain of thought—a series of intermediate reasoning steps—significantly improves the ability of large language models to perform complex reasoning. We show that chain-of-thought prompting is a simple and broadly applicable technique that unlocks reasoning capabilities in large language models.",
            "authors": ["Jason Wei", "Xuezhi Wang", "Dale Schuurmans", "Maarten Bosma"],
            "url": "https://arxiv.org/abs/2201.11903",
            "source": "arxiv",
            "venue": "NeurIPS",
            "published_at": datetime.now() - timedelta(days=90)
        }
    ]
    
    topics = ["LLM", "Agent", "CV", "RL", "Multimodal", "NLP"]
    keywords_list = [
        ["transformer", "attention", "neural network"],
        ["language model", "pre-training", "bert"],
        ["gpt", "multimodal", "large language model"],
        ["ai safety", "constitutional ai", "harmlessness"],
        ["prompting", "reasoning", "chain-of-thought"]
    ]
    
    scoring_system = ScoringSystem()
    
    async with AsyncSessionLocal() as db:
        for i, paper_data in enumerate(papers_data):
            existing = await PaperCRUD.get_paper_by_url(db, paper_data["url"])
            if existing:
                print(f"Paper already exists: {paper_data['title']}")
                continue
            
            paper_create = PaperCreate(**paper_data)
            paper = await PaperCRUD.create_paper(db, paper_create)
            
            summary = f"This paper introduces {paper_data['title'].split(':')[0]}."
            keywords = keywords_list[i] if i < len(keywords_list) else ["ai", "machine learning"]
            topic = topics[i % len(topics)]
            
            await PaperCRUD.create_paper_features(
                db,
                paper.id,
                summary,
                keywords,
                None,
                topic
            )
            
            recency_score = scoring_system.compute_recency_score(paper.published_at)
            venue_score = scoring_system.compute_venue_score(paper.venue, paper.source)
            trend_score = random.uniform(0.3, 0.9)
            final_score = scoring_system.compute_final_score(recency_score, venue_score, trend_score)
            
            await PaperCRUD.create_paper_score(
                db,
                paper.id,
                recency_score,
                venue_score,
                trend_score,
                final_score
            )
            
            print(f"Added paper: {paper.title}")
        
        await db.commit()
    
    print("\nSample papers added successfully!")

if __name__ == "__main__":
    asyncio.run(add_sample_papers())
