from typing import List, Optional, Tuple
import openai
from app.config import settings
import logging
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity
import asyncio

logger = logging.getLogger(__name__)


class AIProcessor:
    def __init__(self):
        if settings.openai_api_key:
            self.client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        else:
            self.client = None
            logger.warning("OpenAI API key not set. AI features will be limited.")
        
        self.topic_keywords = {
            "LLM": ["language model", "gpt", "bert", "transformer", "llm", "large language", "generation", "prompt"],
            "Agent": ["agent", "autonomous", "planning", "tool use", "reasoning", "multi-agent"],
            "CV": ["computer vision", "image", "video", "detection", "segmentation", "recognition", "visual"],
            "RL": ["reinforcement learning", "reward", "policy", "q-learning", "actor-critic", "exploration"],
            "Multimodal": ["multimodal", "vision-language", "cross-modal", "text-to-image", "audio-visual"],
            "NLP": ["natural language", "text", "sentiment", "translation", "parsing", "question answering"],
            "Generative": ["generative", "gan", "diffusion", "vae", "synthesis", "generation"]
        }
        
        self.economics_keywords = {
            "Macroeconomics": [
                "economic growth", "monetary policy", "fiscal policy", "gdp", "gross domestic product",
                "inflation", "unemployment", "interest rate", "exchange rate", "central bank",
                "aggregate demand", "aggregate supply", "business cycle", "recession", "macroeconomic",
                "money supply", "government spending", "tax policy", "stabilization policy"
            ],
            "Microeconomics": [
                "consumer behavior", "consumer theory", "producer theory", "production theory",
                "market equilibrium", "game theory", "nash equilibrium", "supply and demand",
                "price theory", "utility maximization", "profit maximization", "market structure",
                "perfect competition", "monopoly", "oligopoly", "externalities", "public goods",
                "welfare economics", "pareto efficiency", "consumer surplus", "producer surplus"
            ],
            "Econometrics": [
                "regression analysis", "time series", "panel data", "econometric model",
                "statistical inference", "hypothesis testing", "maximum likelihood", "gmm",
                "instrumental variable", "endogeneity", "causality", "identification",
                "cointegration", "unit root", "var", "vector autoregression", "arch", "garch",
                "difference in differences", "regression discontinuity", "propensity score"
            ],
            "Financial Economics": [
                "financial market", "asset pricing", "risk management", "portfolio",
                "stock market", "bond market", "derivatives", "options", "futures",
                "capital asset pricing model", "capm", "efficient market", "behavioral finance",
                "corporate finance", "capital structure", "dividend policy", "mergers and acquisitions",
                "financial crisis", "systemic risk", "credit risk", "market risk", "volatility"
            ],
            "Industrial Economics": [
                "industrial organization", "market structure", "market competition",
                "firm behavior", "corporate behavior", "industrial policy", "antitrust",
                "regulation", "monopoly power", "market power", "entry barriers", "exit",
                "product differentiation", "advertising", "research and development", "innovation",
                "vertical integration", "horizontal integration", "strategic behavior", "pricing strategy"
            ],
            "Development Economics": [
                "economic development", "developing countries", "poverty", "income distribution",
                "inequality", "institutional change", "institutional economics", "human capital",
                "education", "health", "demographic transition", "urbanization", "rural development",
                "foreign aid", "debt relief", "structural transformation", "industrialization",
                "technology adoption", "microfinance", "development policy"
            ],
            "International Economics": [
                "international trade", "trade policy", "tariff", "trade agreement",
                "exchange rate", "foreign exchange", "forex", "international finance",
                "balance of payments", "current account", "capital account", "foreign direct investment",
                "fdi", "multinational corporation", "globalization", "trade liberalization",
                "comparative advantage", "heckscher-ohlin", "gravity model", "currency crisis"
            ]
        }
    
    async def generate_summary(self, abstract: str, title: str) -> Optional[str]:
        if not self.client:
            return self._extract_first_sentences(abstract, 2)
        
        try:
            prompt = f"""Summarize this AI research paper in 1-2 plain English sentences:

Title: {title}
Abstract: {abstract}

Summary:"""
            
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return self._extract_first_sentences(abstract, 2)
    
    async def extract_keywords(self, abstract: str, title: str) -> List[str]:
        if not self.client:
            return self._extract_keywords_simple(abstract)
        
        try:
            prompt = f"""Extract 3-5 key technical keywords from this AI research paper:

Title: {title}
Abstract: {abstract}

Return only the keywords as a comma-separated list:"""
            
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.5
            )
            
            keywords_text = response.choices[0].message.content.strip()
            keywords = [kw.strip() for kw in keywords_text.split(",")]
            return keywords[:5]
            
        except Exception as e:
            logger.error(f"Error extracting keywords: {e}")
            return self._extract_keywords_simple(abstract)
    
    async def compute_embedding(self, text: str) -> Optional[str]:
        if not self.client:
            return None
        
        try:
            response = await self.client.embeddings.create(
                model="text-embedding-ada-002",
                input=text[:8000]
            )
            
            embedding = response.data[0].embedding
            return str(embedding)
            
        except Exception as e:
            logger.error(f"Error computing embedding: {e}")
            return None
    
    async def classify_topic(self, abstract: str, title: str) -> Optional[str]:
        combined_text = f"{title} {abstract}".lower()
        
        topic_scores = {}
        for topic, keywords in self.topic_keywords.items():
            score = sum(1 for keyword in keywords if keyword in combined_text)
            if score > 0:
                topic_scores[topic] = score
        
        if topic_scores:
            return max(topic_scores.items(), key=lambda x: x[1])[0]
        
        return "Other"
    
    async def classify_economics_topic(self, abstract: str, title: str) -> Optional[str]:
        combined_text = f"{title} {abstract}".lower()
        
        topic_scores = {}
        for topic, keywords in self.economics_keywords.items():
            score = sum(1 for keyword in keywords if keyword in combined_text)
            if score > 0:
                topic_scores[topic] = score
        
        if topic_scores:
            return max(topic_scores.items(), key=lambda x: x[1])[0]
        
        return "General Economics"
    
    async def process_paper(self, abstract: str, title: str) -> Tuple[Optional[str], List[str], Optional[str], Optional[str]]:
        tasks = [
            self.generate_summary(abstract, title),
            self.extract_keywords(abstract, title),
            self.compute_embedding(f"{title} {abstract}"),
            self.classify_topic(abstract, title)
        ]
        
        results = await asyncio.gather(*tasks)
        return results
    
    def _extract_first_sentences(self, text: str, num_sentences: int = 2) -> str:
        sentences = text.split('. ')[:num_sentences]
        return '. '.join(sentences) + ('.' if not sentences[-1].endswith('.') else '')
    
    def _extract_keywords_simple(self, text: str) -> List[str]:
        words = text.lower().split()
        keywords = []
        
        ai_keywords = [
            "neural", "deep", "learning", "transformer", "attention", 
            "optimization", "training", "model", "network", "architecture",
            "embedding", "representation", "feature", "layer"
        ]
        
        for word in words:
            clean_word = ''.join(e for e in word if e.isalnum())
            if clean_word in ai_keywords and clean_word not in keywords:
                keywords.append(clean_word)
                if len(keywords) >= 5:
                    break
        
        return keywords


class TrendAnalyzer:
    def __init__(self):
        self.n_clusters = 10
    
    def cluster_papers(self, embeddings: np.ndarray) -> np.ndarray:
        if len(embeddings) < self.n_clusters:
            return np.zeros(len(embeddings), dtype=int)
        
        kmeans = KMeans(n_clusters=min(self.n_clusters, len(embeddings)), random_state=42)
        return kmeans.fit_predict(embeddings)
    
    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        return cosine_similarity([embedding1], [embedding2])[0][0]
    
    def find_similar_papers(
        self,
        target_embedding: np.ndarray,
        all_embeddings: np.ndarray,
        paper_ids: List[str],
        top_k: int = 5
    ) -> List[Tuple[str, float]]:
        if len(all_embeddings) == 0:
            return []
        
        similarities = cosine_similarity([target_embedding], all_embeddings)[0]
        
        top_indices = np.argsort(similarities)[::-1][:top_k + 1]
        
        results = []
        for idx in top_indices:
            if similarities[idx] < 0.99:
                results.append((paper_ids[idx], float(similarities[idx])))
        
        return results[:top_k]
