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

        # Validointi: tarkista että on article
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

        # Guard against missing titles
        enriched_title = getattr(article, "enriched_title", None)
        original_title = getattr(article, "original_title", None)
        title_preview = str(enriched_title or original_title or "Unknown title")[:50]
        
        rejection_reason = self._get_rejection_reason(state)
        
        print(f"📰 Rejecting article: {title_preview}...")
        print(f"🔢 News Article ID: {article.news_article_id}")
        print(f"   💬 Reason: {rejection_reason}")

        try:
            with psycopg.connect(self.db_dsn) as conn:
                # Käytä autocommit=False varmistamaan että transaktio toimii oikein
                conn.autocommit = False
                
                try:
                    # Get current timestamp
                    rejected_at = datetime.datetime.now(datetime.timezone.utc)

                    # 1. Update news_article status to rejected (RETURNING lisätty)
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
                            f"⚠️  No rows updated - article {article.news_article_id} not found in database!"
                        )
                        conn.rollback()
                        return state

                    # Varmista että status todella päivittyi
                    updated_id, updated_status = updated_row
                    print(f"✅ Article status updated to '{updated_status}' successfully!")
                    print(f"   🆔 Updated article ID: {updated_id}")

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
                            import traceback
                            traceback.print_exc()
                    else:
                        print(
                            "⚠️ No review_result found - skipping editorial review save"
                        )

                    conn.commit()
                    print(f"✅ Database transaction committed successfully!")
                    print(f"   📅 Rejected at: {rejected_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    
                    # LISÄ-VARMISTUS: Tarkista että status todella päivittyi tietokantaan
                    verify_cursor = conn.execute(
                        "SELECT status FROM news_article WHERE id = %s",
                        (article.news_article_id,)
                    )
                    verify_result = verify_cursor.fetchone()
                    
                    if verify_result:
                        print(f"🔍 Verification: Database status is now '{verify_result[0]}'")
                        if verify_result[0] != 'rejected':
                            print(f"⚠️⚠️⚠️ WARNING: Status mismatch! Expected 'rejected', got '{verify_result[0]}'")
                    else:
                        print(f"⚠️ Could not verify database status!")
                
                except Exception as tx_error:
                    # Rollback jos jotain menee pieleen
                    conn.rollback()
                    print(f"❌ Transaction failed, rolled back: {tx_error}")
                    import traceback
                    traceback.print_exc()
                    raise

        except psycopg.Error as db_error:
            print(f"❌ Database error in ArticleRejectAgent: {db_error}")
            import traceback
            traceback.print_exc()
        except Exception as e:
            print(f"❌ Unexpected error rejecting article: {e}")
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
                explanation = state.review_result.editorial_reasoning.explanation
                if explanation:
                    return explanation
        return "Editorial rejection - no specific reason provided"