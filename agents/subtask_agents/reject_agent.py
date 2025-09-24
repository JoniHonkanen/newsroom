from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle
import psycopg
import datetime

from services.editor_review_service import EditorialReviewService


class ArticleRejectAgent(BaseAgent):
    """Agent that handles rejected articles by updating their status and saving rejection review."""

    def __init__(self, db_dsn: str):
        super().__init__(llm=None, prompt=None, name="ArticleRejectAgent")
        self.db_dsn = db_dsn
        self.editorial_service = EditorialReviewService(db_dsn)

    def run(self, state: AgentState) -> AgentState:
        """Updates the rejected article's status and saves editorial review."""
        print("🚫 ARTICLE REJECT AGENT: Processing rejected article...")

        if not hasattr(state, "current_article") or not state.current_article:
            print("❌ ArticleRejectAgent: No current_article to reject!")
            return state

        article: EnrichedArticle = state.current_article
        if not isinstance(article, EnrichedArticle):
            print(
                f"❌ ArticleRejectAgent: Expected EnrichedArticle, got {type(article)}"
            )
            return state

        if not article.news_article_id:
            print("❌ ArticleRejectAgent: Article has no news_article_id!")
            return state

        print(f"📰 Rejecting article: {article.enriched_title[:50]}...")
        print(f"🔢 News Article ID: {article.news_article_id}")
        print(f"   💬 Reason: {self._get_rejection_reason(state)}")

        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.transaction():
                    # Get current timestamp
                    rejected_at = datetime.datetime.now(datetime.timezone.utc)

                    # 1. Update news_article status to rejected
                    result = conn.execute(
                        """
                        UPDATE news_article
                        SET 
                            status = 'rejected',
                            updated_at = %s
                        WHERE id = %s
                        """,
                        (rejected_at, article.news_article_id),
                    )

                    if result.rowcount == 0:
                        print(
                            f"⚠️  No rows updated - article {article.news_article_id} not found!"
                        )
                        return state

                    print("✅ Article status updated to 'rejected' successfully!")

                    # 2. Save editorial review (rejection audit trail)
                    if hasattr(state, "review_result") and state.review_result:
                        try:
                            editorial_review_id = (
                                self.editorial_service.save_editorial_review(
                                    news_article_id=article.news_article_id,
                                    review_data=state.review_result,
                                )
                            )
                            print(
                                f"💾 Rejection review saved to editorial_reviews (ID: {editorial_review_id})"
                            )
                        except Exception as review_error:
                            print(f"⚠️ Failed to save editorial review: {review_error}")
                            # Don't fail the whole process if audit fails
                    else:
                        print(
                            "⚠️ No review_result found - skipping editorial review save"
                        )

                    print(
                        f"   📅 Rejected at: {rejected_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )

        except Exception as e:
            print(f"❌ Error rejecting article: {e}")
            import traceback

            traceback.print_exc()

        return state

    def _get_rejection_reason(self, state: AgentState) -> str:
        """Extract rejection reason from review_result."""
        if hasattr(state, "review_result") and state.review_result:
            if (
                hasattr(state.review_result, "editorial_reasoning")
                and state.review_result.editorial_reasoning
            ):
                return state.review_result.editorial_reasoning.explanation
        return "Editorial rejection - no specific reason provided"
