from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle
import psycopg
import datetime
import sys

from services.editor_review_service import EditorialReviewService


class ArticleRejectAgent(BaseAgent):
    """Agent that handles rejected articles by updating their status and saving rejection review."""

    def __init__(self, db_dsn: str):
        super().__init__(llm=None, prompt=None, name="ArticleRejectAgent")
        self.db_dsn = db_dsn
        self.editorial_service = EditorialReviewService(db_dsn)

    def run(self, state: AgentState) -> AgentState:
        """Updates the rejected article's status and saves editorial review."""
        print("🚫 ARTICLE REJECT AGENT: Processing rejected article...", flush=True)

        if not hasattr(state, "current_article") or not state.current_article:
            print("❌ ArticleRejectAgent: No current_article to reject!", flush=True)
            return state

        article: EnrichedArticle = state.current_article
        if not isinstance(article, EnrichedArticle):
            print(
                f"❌ ArticleRejectAgent: Expected EnrichedArticle, got {type(article)}",
                flush=True,
            )
            return state

        if not article.news_article_id:
            print("❌ ArticleRejectAgent: Article has no news_article_id!", flush=True)
            return state

        enriched_title = getattr(article, "enriched_title", None)
        original_title = getattr(article, "original_title", None)
        title_preview = str(enriched_title or original_title or "Unknown title")[:50]

        rejection_reason = self._get_rejection_reason(state)

        print(f"📰 Rejecting article: {title_preview}...", flush=True)
        print(f"🔢 News Article ID: {article.news_article_id}", flush=True)
        print(f"   💬 Reason: {rejection_reason}", flush=True)

        try:
            with psycopg.connect(self.db_dsn) as conn:
                conn.autocommit = False
                try:
                    rejected_at = datetime.datetime.now(datetime.timezone.utc)

                    cursor = conn.execute(
                        """
                        UPDATE news_article
                        SET 
                            status = 'rejected',
                            updated_at = %s
                        WHERE id = %s
                        RETURNING id, status
                        """,
                        (rejected_at, article.news_article_id),
                    )
                    updated_row = cursor.fetchone()
                    if not updated_row:
                        print(
                            f"⚠️  No rows updated - article {article.news_article_id} not found!",
                            flush=True,
                        )
                        conn.rollback()
                        return state

                    updated_id, updated_status = updated_row
                    print(
                        f"✅ Article status updated to '{updated_status}' successfully!",
                        flush=True,
                    )
                    print(f"   🆔 Updated article ID: {updated_id}", flush=True)

                    # IMPORTANT: Commit the article rejection BEFORE saving editorial review
                    # to avoid cross-connection lock waits if the review saving touches
                    # related tables (or even news_article in some cases).
                    conn.commit()
                    print(f"✅ Transaction committed successfully!", flush=True)
                    print(
                        f"   📅 Rejected at: {rejected_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                        flush=True,
                    )

                    # Now save the rejection review in a separate connection safely
                    if hasattr(state, "review_result") and state.review_result:
                        try:
                            print("📝 Saving rejection editorial review...", flush=True)
                            editorial_review_id = (
                                self.editorial_service.save_editorial_review(
                                    news_article_id=article.news_article_id,
                                    review_data=state.review_result,
                                )
                            )
                            print(
                                f"💾 Rejection review saved (ID: {editorial_review_id})",
                                flush=True,
                            )
                        except Exception as review_error:
                            print(
                                f"⚠️ Failed to save editorial review: {review_error}",
                                flush=True,
                            )

                except Exception as tx_error:
                    conn.rollback()
                    print(f"❌ Transaction failed, rolled back: {tx_error}", flush=True)
                    import traceback

                    traceback.print_exc()
                    return state

        except psycopg.Error as db_error:
            print(f"❌ Database error in ArticleRejectAgent: {db_error}", flush=True)
            import traceback

            traceback.print_exc()
            return state

        except Exception as e:
            print(f"❌ Unexpected error rejecting article: {e}", flush=True)
            import traceback

            traceback.print_exc()
            return state

        print(f"🔄 ArticleRejectAgent completed, returning state...", flush=True)
        sys.stdout.flush()
        return state

    def _get_rejection_reason(self, state: AgentState) -> str:
        """Extract rejection reason from review_result."""
        if hasattr(state, "review_result") and state.review_result:
            if (
                hasattr(state.review_result, "editorial_reasoning")
                and state.review_result.editorial_reasoning
            ):
                explanation = state.review_result.editorial_reasoning.explanation
                if explanation:
                    return explanation
        return "Editorial rejection - no specific reason provided"
