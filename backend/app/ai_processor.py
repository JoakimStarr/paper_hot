from typing import List, Optional, Tuple
import logging
import asyncio
import math

logger = logging.getLogger(__name__)


class AIProcessor:
    def __init__(self):
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

        self._all_keywords = set()
        for kws in self.topic_keywords.values():
            self._all_keywords.update(kws)
        for kws in self.economics_keywords.values():
            self._all_keywords.update(kws)

    def generate_summary(self, abstract: str, title: str) -> str:
        return self._extract_first_sentences(abstract, 2)

    def extract_keywords(self, abstract: str, title: str) -> List[str]:
        combined_text = f"{title} {abstract}".lower()

        keyword_scores = {}
        for kw in self._all_keywords:
            count = combined_text.count(kw)
            if count > 0:
                keyword_scores[kw] = count

        sorted_keywords = sorted(keyword_scores.items(), key=lambda x: x[1], reverse=True)

        result = [kw for kw, _ in sorted_keywords[:5]]
        return result

    def compute_embedding(self, text: str) -> Optional[str]:
        return None

    def classify_topic(self, abstract: str, title: str) -> Optional[str]:
        combined_text = f"{title} {abstract}".lower()

        topic_scores = {}
        for topic, keywords in self.topic_keywords.items():
            score = sum(1 for keyword in keywords if keyword in combined_text)
            if score > 0:
                topic_scores[topic] = score

        if topic_scores:
            return max(topic_scores.items(), key=lambda x: x[1])[0]

        return None

    def classify_economics_topic(self, abstract: str, title: str) -> Optional[str]:
        combined_text = f"{title} {abstract}".lower()

        topic_scores = {}
        for topic, keywords in self.economics_keywords.items():
            score = sum(1 for keyword in keywords if keyword in combined_text)
            if score > 0:
                topic_scores[topic] = score

        if topic_scores:
            return max(topic_scores.items(), key=lambda x: x[1])[0]

        return "General Economics"

    async def process_paper(self, abstract: str, title: str) -> Tuple[str, List[str], Optional[str], Optional[str]]:
        summary = self.generate_summary(abstract, title)
        keywords = self.extract_keywords(abstract, title)
        embedding = None
        topic = self.classify_topic(abstract, title)

        return summary, keywords, embedding, topic

    def _extract_first_sentences(self, text: str, num_sentences: int = 2) -> str:
        sentences = text.split('. ')[:num_sentences]
        return '. '.join(sentences) + ('.' if not sentences[-1].endswith('.') else '')