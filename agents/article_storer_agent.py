# File: agents/article_storer_agent.py

import sys
import os

# Add the project root to the Python path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle
from services.news_article_service import NewsArticleService
from typing import List


class ArticleStorerAgent(BaseAgent):
    """An agent that stores enriched articles in the database."""

    def __init__(self, db_dsn: str):
        super().__init__(llm=None, prompt=None, name="ArticleStorerAgent")
        self.article_service = NewsArticleService(db_dsn=db_dsn)

    def run(self, state: AgentState) -> AgentState:
        """Runs the article storer agent to store enriched articles in the database."""
        print(
            "ArticleStorerAgent: Starting to store enriched articles in the database..."
        )

        enriched_articles: List[EnrichedArticle] = state.enriched_articles

        canonical_ids: dict = state.canonical_ids

        if not enriched_articles:
            print("ArticleStorerAgent: No enriched articles to store.")
            return state

        print(
            f"ArticleStorerAgent: Storing {len(enriched_articles)} enriched articles..."
        )

        stored_article_ids: List[int] = []

        for article in enriched_articles:
            try:
                # Log if canonical_news_id is set from the previous step
                if article.canonical_news_id:
                    print(
                        f"  - Using canonical_news_id: {article.canonical_news_id} for article: {article.article_id}"
                    )
                else:
                    # Check if we have the canonical ID in our state mapping
                    if article.article_id in canonical_ids:
                        article.canonical_news_id = canonical_ids[article.article_id]
                        print(
                            f"  - Found canonical_news_id: {article.canonical_news_id} from state mapping"
                        )
                    else:
                        print(
                            f"  - No canonical_news_id found for article: {article.article_id}"
                        )

                article_id = self.article_service.save_enriched_article(article)
                stored_article_ids.append(article_id)
                article.news_article_id = (
                    article_id  # we will use this in editor_in_chief_agent
                )
                print(
                    f"  - Stored article with ID {article_id}: {article.enriched_title}"
                )
            except Exception as e:
                print(f"  - Failed to store article: {e}")

        # We don't need to store article_ids in state anymore as we use canonical_ids for tracking

        return state


# ======================================================================
# Standalone Test Runner
# ======================================================================
if __name__ == "__main__":
    from dotenv import load_dotenv
    import os
    from datetime import datetime

    print("--- Running ArticleStorerAgent in isolation for testing ---")
    load_dotenv()

    # Get DB config from environment variables
    db_dsn = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

    # Create a mock enriched article
    mock_article = EnrichedArticle(
        article_id="http://test.fi/suomi-ai",
        enriched_title="Finland's AI Strategy Expands with New Investments",
        enriched_content="""
# Finland's AI Strategy Expands with New Investments

Finland is strengthening its position as a leader in artificial intelligence through increased funding and education initiatives. The government has announced plans to invest heavily in AI research and education.

## New Research Centers

The Finnish government is establishing three new AI research centers in Helsinki, Tampere, and Oulu. These centers will focus on developing ethical AI applications for healthcare, education, and environmental monitoring.

## Educational Programs

Universities across Finland are expanding their AI curricula to ensure a pipeline of skilled AI professionals. These programs aim to make Finland a global leader in AI talent development.
""",
        published_at="2023-01-15",
        generated_at=datetime.now().isoformat(),
        source_domain="test.fi",
        keywords=["Finland", "AI", "investment", "education", "technology"],
        categories=["Technology", "Politics", "Education"],
        language="en",
        sources=["https://example.com/finland-ai"],
        locations=[
            {
                "continent": "Europe",
                "country": "Finland",
                "region": None,
                "city": "Helsinki",
            }
        ],
        references=[
            {
                "title": "Finnish AI Strategy Document",
                "url": "https://example.com/finnish-ai-strategy",
            }
        ],
    )

    # Set up mock state with the enriched article
    class MockAgentState:
        def __init__(self):
            self.enriched_articles = [mock_article]
            self.stored_article_ids = []

    # Create and run the agent
    storer_agent = ArticleStorerAgent(db_dsn=db_dsn)
    initial_state = MockAgentState()

    print("\n--- Invoking the agent's run method... ---")
    result_state = storer_agent.run(initial_state)
    print("--- Agent run completed. ---")

    print("\n--- Results ---")
    print(f"Stored article IDs: {getattr(result_state, 'stored_article_ids', [])}")
