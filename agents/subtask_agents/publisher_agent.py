# File: agents/article_publisher_agent.py

from typing import Any
from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle
from sentence_transformers import SentenceTransformer
import psycopg
import datetime


class ArticlePublisherAgent(BaseAgent):
    """Agent that publishes approved articles: updates status to 'published', sets publish date, and creates embeddings."""

    def __init__(self, db_dsn: str):
        super().__init__(llm=None, prompt=None, name="ArticlePublisherAgent")
        self.db_dsn = db_dsn
        # Same model as NewsStorerAgent for consistency
        self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    def _encode(self, text: str) -> list[float]:
        """Encode text into a vector using the SentenceTransformer model."""
        return (
            self.model.encode(text, normalize_embeddings=True)
            .astype("float32")
            .tolist()
        )

    def _normalize(self, text: str) -> str:
        """Normalize text by stripping whitespace and removing extra spaces."""
        return " ".join(text.split())

    def run(self, state: AgentState) -> AgentState:
        """Publish the current article by updating database status and creating embeddings."""
        print("ARTICLE PUBLISHER AGENT: Starting to publish the current article...")

        if not hasattr(state, "current_article") or not state.current_article:
            print("❌ ArticlePublisherAgent: No current_article to publish!")
            return state

        article = state.current_article
        if not isinstance(article, EnrichedArticle):
            print(
                f"❌ ArticlePublisherAgent: Expected EnrichedArticle, got {type(article)}"
            )
            return state

        if not article.news_article_id:
            print(f"❌ ArticlePublisherAgent: Article has no news_article_id!")
            return state

        print(f"📰 Publishing article: {article.enriched_title[:50]}...")
        print(f"🔢 News Article ID: {article.news_article_id}")

        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.transaction():
                    # Create embedding from enriched content
                    full_content = (
                        f"{article.enriched_title}\n\n{article.enriched_content}"
                    )
                    normalized_content = self._normalize(full_content)
                    embedding = self._encode(normalized_content)

                    # Get current timestamp
                    published_at = datetime.datetime.now(datetime.timezone.utc)

                    # Update news_article status, publish date, and embedding
                    result = conn.execute(
                        """
                        UPDATE news_article
                        SET 
                            status = 'published',
                            published_at = %s,
                            embedding = %s::vector,
                            updated_at = %s
                        WHERE id = %s
                        """,
                        (
                            published_at,
                            embedding,
                            published_at,
                            article.news_article_id,
                        ),
                    )

                    if result.rowcount == 0:
                        print(
                            f"⚠️  No rows updated - article {article.news_article_id} not found!"
                        )
                        return state

                    print(f"✅ Article published successfully!")
                    print(
                        f"   📅 Published at: {published_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )
                    print(f"   🔢 Embedding dimensions: {len(embedding)}")

                    # Update article object with publish info
                    article.published_at = published_at.isoformat()

        except Exception as e:
            print(f"❌ Error publishing article: {e}")
            import traceback

            traceback.print_exc()

        return state


# Test runner
if __name__ == "__main__":
    from dotenv import load_dotenv
    from schemas.enriched_article import EnrichedArticle
    import os

    load_dotenv()
    db_dsn = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/newsdb")

    # Mock enriched article for testing
    test_article = EnrichedArticle(
        article_id="test-123",
        canonical_news_id=1,
        news_article_id=1,  # Would come from ArticleStorerAgent
        enriched_title="Test Article Title",
        enriched_content="This is the enriched content of the test article with additional context and information.",
        published_at="2025-01-15T10:00:00Z",
        source_domain="test.fi",
        keywords=["test", "article"],
        categories=["Technology"],
        language="fi",
        sources=["https://example.com/source"],
        references=[],
        locations=[],
        summary="Test article summary",
        enrichment_status="success",
    )

    # Mock state
    class MockState:
        def __init__(self):
            self.current_article = test_article

    # Test the agent
    try:
        agent = ArticlePublisherAgent(db_dsn)
        result = agent.run(MockState())
        print("✅ Test completed!")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
