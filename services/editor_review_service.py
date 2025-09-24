"""
Editorial Review Service - Simple version following NewsArticleService pattern
"""

import psycopg
from psycopg.types.json import Jsonb
from typing import List, Optional, Dict, Any
from datetime import datetime
from schemas.editor_in_chief_schema import ReviewedNewsItem, ReasoningStep


class EditorialReviewService:
    """Service for managing editorial review data - simple and clean like NewsArticleService"""

    def __init__(self, db_dsn: str):
        """Initialize with database connection string"""
        self.db_dsn = db_dsn
        print(f"🔗 Initializing EditorialReviewService with DSN: {db_dsn[:50]}...")
        self._setup_tables()
        print("✅ EditorialReviewService initialized successfully")

    def _setup_tables(self):
        """Ensure database tables and indexes exist"""
        with psycopg.connect(self.db_dsn) as conn:
            with conn.cursor() as cur:
                # Create helpful indexes if they don't exist
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_editorial_reviews_article_id ON editorial_reviews(article_id);
                    CREATE INDEX IF NOT EXISTS idx_editorial_reviews_status ON editorial_reviews(status);
                    CREATE INDEX IF NOT EXISTS idx_editorial_reviews_reviewer ON editorial_reviews(reviewer);
                    CREATE INDEX IF NOT EXISTS idx_editorial_reviews_created_at ON editorial_reviews(created_at);
                    CREATE INDEX IF NOT EXISTS idx_editorial_reviews_featured ON editorial_reviews(featured);
                    CREATE INDEX IF NOT EXISTS idx_editorial_issues_article_id ON editorial_issues(article_id);
                    CREATE INDEX IF NOT EXISTS idx_editorial_reasoning_steps_article_id ON editorial_reasoning_steps(article_id);
                """
                )
                conn.commit()

    def save_review(self, article_id: str, review: ReviewedNewsItem) -> bool:
        """
        Save editorial review decision to database

        Args:
            article_id: Unique identifier for the generated news article
            review: ReviewedNewsItem object containing the full review decision

        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    # Determine final decision
                    final_decision = None
                    if review.reconsideration:
                        final_decision = review.reconsideration.final_decision
                    elif review.editorial_reasoning.initial_decision:
                        final_decision = review.editorial_reasoning.initial_decision

                    # Extract featured status
                    featured = (
                        review.headline_news_assessment.featured
                        if review.headline_news_assessment
                        else False
                    )

                    # Extract interview decision data
                    interview_needed = (
                        review.interview_decision.interview_needed
                        if review.interview_decision
                        else False
                    )

                    interview_decision_json = (
                        Jsonb(review.interview_decision.model_dump())
                        if review.interview_decision
                        else None
                    )

                    # Use consistent timestamp for both created_at and updated_at
                    now = datetime.now()

                    # Insert/Update main review record - interview_decision tallennetaan vain review_data:han
                    cur.execute(
                        """
                            INSERT INTO editorial_reviews 
                            (article_id, review_data, status, reviewer, initial_decision, 
                             final_decision, has_warning, featured, interview_decision, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (article_id) 
                            DO UPDATE SET 
                                review_data = EXCLUDED.review_data,
                                status = EXCLUDED.status,
                                final_decision = EXCLUDED.final_decision,
                                has_warning = EXCLUDED.has_warning,
                                featured = EXCLUDED.featured,
                                interview_decision = EXCLUDED.interview_decision,
                                updated_at = EXCLUDED.updated_at
                        """,
                        (
                            article_id,
                            Jsonb(review.model_dump()),
                            review.status,
                            review.editorial_reasoning.reviewer,
                            review.editorial_reasoning.initial_decision,
                            final_decision,
                            review.editorial_warning is not None,
                            featured,
                            interview_decision_json,
                            now,
                            now,
                        ),
                    )

                    # OPTIMIZED: Update news_article table only when values are true
                    # (both featured and interview_decision default to false, no need to update false values)
                    updates_needed = []
                    params = []

                    if featured:
                        updates_needed.append("featured = true")

                    if interview_needed:
                        # Store interview flag on news_article using the correct column
                        updates_needed.append("interview_decision = true")

                    # Only update if we have something to update
                    if updates_needed:
                        updates_needed.append("updated_at = %s")
                        params.append(now)
                        params.append(article_id)

                        update_sql = f"""
                            UPDATE news_article 
                            SET {', '.join(updates_needed)}
                            WHERE id = %s
                        """

                        cur.execute(update_sql, params)

                    # Clear and re-insert related data
                    cur.execute(
                        "DELETE FROM editorial_issues WHERE article_id = %s",
                        (article_id,),
                    )
                    cur.execute(
                        "DELETE FROM editorial_reasoning_steps WHERE article_id = %s",
                        (article_id,),
                    )

                    # Insert issues
                    for issue in review.issues:
                        cur.execute(
                            """
                            INSERT INTO editorial_issues 
                            (article_id, issue_type, location, description, suggestion)
                            VALUES (%s, %s, %s, %s, %s)
                        """,
                            (
                                article_id,
                                issue.type,
                                issue.location,
                                issue.description,
                                issue.suggestion,
                            ),
                        )

                    # Insert reasoning steps
                    self._insert_reasoning_steps(
                        cur,
                        article_id,
                        review.editorial_reasoning.reasoning_steps,
                        False,
                    )

                    # Insert reconsideration steps if present
                    if review.reconsideration:
                        self._insert_reasoning_steps(
                            cur,
                            article_id,
                            review.reconsideration.reasoning_steps,
                            True,
                        )

                    conn.commit()
                    print(f"✅ Successfully saved review for article {article_id}")
                    print(f"   - Editorial review: ✅")

                    # Better logging for news_article updates
                    if featured and interview_needed:
                        print(
                            f"   - News article: ✅ UPDATED (featured=true, interview_decision=true)"
                        )
                    elif featured:
                        print(f"   - News article: ✅ UPDATED (featured=true)")
                    elif interview_needed:
                        print(f"   - News article: ✅ UPDATED (interview_decision=true)")
                    else:
                        print(f"   - News article: ❌ (no updates needed - both false)")

                    print(
                        f"   - Interview decision: {'✅ SAVED' if review.interview_decision else '❌ MISSING'}"
                    )
                    print(f"   - Issues: {len(review.issues)} saved")
                    print(
                        f"   - Reasoning steps: {len(review.editorial_reasoning.reasoning_steps)} saved"
                    )
                    if review.reconsideration:
                        print(
                            f"   - Reconsideration steps: {len(review.reconsideration.reasoning_steps)} saved"
                        )
                    return True

        except Exception as e:
            print(f"Error saving editorial review for article {article_id}: {e}")
            return False

    def _insert_reasoning_steps(
        self,
        cur,
        article_id: str,
        steps: List[ReasoningStep],
        is_reconsideration: bool,
    ):
        """Helper method to insert reasoning steps"""
        for step in steps:
            cur.execute(
                """
                INSERT INTO editorial_reasoning_steps 
                (article_id, step_id, action, observation, result, is_reconsideration)
                VALUES (%s, %s, %s, %s, %s, %s)
            """,
                (
                    article_id,
                    step.step_id,
                    step.action,
                    step.observation,
                    step.result,
                    is_reconsideration,
                ),
            )

    def save_editorial_review(
        self, news_article_id: int, review_data: ReviewedNewsItem
    ) -> int:
        """
        Alias for save_review to maintain compatibility with ArticleRejectAgent.
        Args:
            news_article_id: Integer ID from news_article table
            review_data: ReviewedNewsItem object containing the review
        Returns:
            int: The article_id (for logging purposes)
        """
        # Convert integer ID to string for internal use
        article_id_str = str(news_article_id)
        # Call existing save_review method
        success = self.save_review(article_id_str, review_data)
        if success:
            return news_article_id  # Return original ID for logging
        else:
            raise Exception(
                f"Failed to save editorial review for article {news_article_id}"
            )

    # ***********THESE ARE NOT USED, BUT MAY BE HELPFUL LATER**************
    def get_review(self, article_id: str) -> Optional[ReviewedNewsItem]:
        """Get editorial review by article ID"""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT review_data 
                        FROM editorial_reviews 
                        WHERE article_id = %s
                    """,
                        (article_id,),
                    )

                    result = cur.fetchone()
                    if result:
                        return ReviewedNewsItem(**result[0])
                    return None

        except Exception as e:
            print(f"Error retrieving editorial review for article {article_id}: {e}")
            return None

    def get_articles_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get articles by review status"""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT article_id, review_data, featured, created_at, updated_at
                        FROM editorial_reviews 
                        WHERE status = %s
                        ORDER BY created_at DESC
                    """,
                        (status,),
                    )

                    return [
                        {
                            "article_id": row[0],
                            "review_data": row[1],
                            "featured": row[2],
                            "created_at": row[3],
                            "updated_at": row[4],
                        }
                        for row in cur.fetchall()
                    ]

        except Exception as e:
            print(f"Error retrieving articles by status {status}: {e}")
            return []

    def get_reviewer_stats(self, reviewer: str) -> Dict[str, Any]:
        """Get statistics for a specific reviewer"""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 
                            COUNT(*) as total_reviews,
                            COUNT(CASE WHEN status = 'OK' THEN 1 END) as ok_reviews,
                            COUNT(CASE WHEN status = 'ISSUES_FOUND' THEN 1 END) as issues_found,
                            COUNT(CASE WHEN status = 'RECONSIDERATION' THEN 1 END) as reconsiderations,
                            COUNT(CASE WHEN has_warning = true THEN 1 END) as with_warnings,
                            COUNT(CASE WHEN featured = true THEN 1 END) as featured_articles
                        FROM editorial_reviews 
                        WHERE reviewer = %s
                    """,
                        (reviewer,),
                    )

                    result = cur.fetchone()
                    if result:
                        return {
                            "reviewer": reviewer,
                            "total_reviews": result[0],
                            "ok_reviews": result[1],
                            "issues_found": result[2],
                            "reconsiderations": result[3],
                            "with_warnings": result[4],
                            "featured_articles": result[5],
                        }
                    return {}

        except Exception as e:
            print(f"Error retrieving stats for reviewer {reviewer}: {e}")
            return {}

    def get_articles_with_warnings(self) -> List[Dict[str, Any]]:
        """Get all articles that have editorial warnings"""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT article_id, review_data, featured, created_at
                        FROM editorial_reviews 
                        WHERE has_warning = true
                        ORDER BY created_at DESC
                    """
                    )

                    return [
                        {
                            "article_id": row[0],
                            "review_data": row[1],
                            "featured": row[2],
                            "created_at": row[3],
                        }
                        for row in cur.fetchall()
                    ]

        except Exception as e:
            print(f"Error retrieving articles with warnings: {e}")
            return []

    def get_articles_needing_attention(self) -> List[Dict[str, Any]]:
        """Get articles that need editorial attention (not OK status)"""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT article_id, status, reviewer, featured, created_at, updated_at
                        FROM editorial_reviews 
                        WHERE status != 'OK'
                        ORDER BY updated_at DESC
                    """
                    )

                    return [
                        {
                            "article_id": row[0],
                            "status": row[1],
                            "reviewer": row[2],
                            "featured": row[3],
                            "created_at": row[4],
                            "updated_at": row[5],
                        }
                        for row in cur.fetchall()
                    ]

        except Exception as e:
            print(f"Error retrieving articles needing attention: {e}")
            return []


# Example usage - simple and clean like NewsArticleService
if __name__ == "__main__":
    import os

    # Initialize service - no singleton complexity
    db_dsn = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/newsdb")
    service = EditorialReviewService(db_dsn)

    # Example usage:
    # success = service.save_review("news_article_123", review)
    # review = service.get_review("news_article_123")
    # featured_articles = service.get_featured_articles()
    # stats = service.get_editorial_summary()
    # articles_needing_attention = service.get_articles_needing_attention()

    print("EditorialReviewService (with featured support) ready for use")
