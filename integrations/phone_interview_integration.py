import os
import logging
from typing import Optional, Dict, Any
from langchain.chat_models import init_chat_model
import psycopg  # type: ignore

from agents.interview_agents.article_enricher_agent import ArticleEnricherAgent
from schemas.agent_state import AgentState, InterviewAgentState
from schemas.enriched_article import EnrichedArticle
from services.news_article_service import NewsArticleService
from schemas.interview_schema import DataAfterInterviewFromDatabase

logger = logging.getLogger(__name__)


class PhoneInterviewIntegration:
    """Integration layer for enriching articles with phone interview content."""

    def __init__(self, db_dsn: str, llm_model: str = "gpt-4o-mini"):
        self.db_dsn = db_dsn
        self.llm = init_chat_model(llm_model, model_provider="openai")
        self.enricher_agent = ArticleEnricherAgent(self.llm, db_dsn)
        self.article_service = NewsArticleService(db_dsn)

    def enrich_article_with_phone_interview(
        self,
        article_id: int,
        interview_content: str,
        respondent_name: str,
        respondent_title: str = None,
        respondent_organization: str = None,
    ) -> Dict[str, Any]:
        logger.info(f"Starting phone interview enrichment for article_id: {article_id}")
        logger.info(f"Respondent: {respondent_name}")
        print("Starting phone interview enrichment for article_id:", article_id)

        try:
            # 1. Load article from database
            article: DataAfterInterviewFromDatabase = self._load_article_from_db(
                article_id
            )
            if not article:
                return {
                    "status": "error",
                    "message": f"Article {article_id} not found",
                    "article_id": article_id,
                }

            print("ALKUPERÄINEN ARTIKKELI:", article)
            print("PUHELINHAASTATTELUN SISÄLTÖ:", interview_content)

            # 2. Create simple agent state
            state = InterviewAgentState()
            state.current_article = article
            state.interview_content = interview_content
            state.interview_respondent_name = respondent_name
            state.interview_respondent_title = respondent_title
            state.interview_respondent_organization = respondent_organization

            # 3. Run enrichment agent
            print("Running ArticleEnricherAgent for phone interview...")
            result_state = self.enricher_agent.run(state)
            print("ONKO ARTIKKELI RIKASTETTU ONNISTUNEESTI????: ", result_state)

            # 4. Save enriched article back to database
            if (
                hasattr(result_state, "new_enriched_article")
                and result_state.new_enriched_article
            ):
                enrichment_result = (
                    result_state.new_enriched_article
                )  # EnrichedArticleWithInterview

                # Use enriched content as-is - LLM should handle title formatting properly
                final_markdown = enrichment_result.enriched_content.strip()

                # Update existing news_article using service
                updated = self.article_service.update_article_after_interview(
                    news_article_id=article.article_id,
                    markdown_content=final_markdown,
                    summary=getattr(enrichment_result, "summary", None),
                    revision_increment=1,
                )

                if not updated:
                    return {
                        "status": "error",
                        "message": "Failed to update article in database",
                        "article_id": article_id,
                    }

                logger.info("Phone interview enrichment completed successfully!")

                return {
                    "status": "success",
                    "message": "Article enriched with phone interview successfully",
                    "article_id": article_id,
                    "summary": getattr(enrichment_result, "summary", None),
                    "enrichment_summary": getattr(enrichment_result, "summary", None),
                    "respondent_integrated": f"{respondent_name} ({respondent_organization or 'Independent'})",
                    "enriched_title": enrichment_result.enriched_title,
                    "content_length": len(enrichment_result.enriched_content),
                    "interview_type": "phone",
                }
            else:
                logger.error(
                    "Phone interview enrichment agent failed to produce results"
                )
                return {
                    "status": "error",
                    "message": "Phone interview enrichment agent failed to produce results",
                    "article_id": article_id,
                }

        except Exception as e:
            logger.error(f"Error during phone interview enrichment: {e}")
            import traceback

            traceback.print_exc()

            return {
                "status": "error",
                "message": f"Phone interview enrichment failed: {str(e)}",
                "article_id": article_id,
            }

    def _load_article_from_db(self, article_id: int) -> DataAfterInterviewFromDatabase:
        """Load article from database."""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, lead, markdown_content, language
                        FROM news_article
                        WHERE id = %s
                    """,
                        (article_id,),
                    )

                    row = cur.fetchone()
                    if not row:
                        return None

                    id, lead, content, language = row

                    return DataAfterInterviewFromDatabase(
                        article_id=id,
                        enriched_title=lead,
                        enriched_content=content,
                        language=language,
                    )

        except psycopg.Error as e:
            logger.error(f"Database error loading article: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading article: {e}")
            return None


# YKSINKERTAINEN FUNKTIO ULKOISEN SERVERIN KÄYTTÖÖN
def enrich_article_with_phone_call(
    article_id: str,
    call_content: str,
) -> Dict[str, Any]:
    """
    Yksinkertainen funktio artikkelien rikastamiseen puhelinhaastatteluilla.
    Sama pattern kuin sähköpostiversiossa.

    Args:
        article_id: Artiklin ID (string webhook payloadista)
        call_content: Puhelinhaastattelun sisältö (litterointi, yhteenveto, tms.)
    """
    print("ENRICHING ARTICLE WITH PHONE CALL!!!!!! :;DDD")

    try:
        # Muunna article_id integeriksi
        article_id_int = int(article_id)
    except ValueError:
        return {
            "status": "error",
            "message": f"Invalid article_id format: {article_id}",
            "article_id": article_id,
        }

    # Hae yhteystiedot article_id:n perusteella (sama logiikka kuin sähköpostissa)
    contact_info = _get_contact_info_by_article_id(article_id_int)
    print("CONTACT INFO:", contact_info)

    if not contact_info:
        # Fallback: käytä geneeristä nimeä
        contact_info = {
            "respondent_name": "Haastateltava",
            "respondent_title": None,
            "respondent_organization": None,
        }

    db_dsn = os.getenv("DATABASE_URL")
    integration = PhoneInterviewIntegration(db_dsn)

    return integration.enrich_article_with_phone_interview(
        article_id_int,
        call_content,
        contact_info["respondent_name"],
        contact_info.get("respondent_title"),
        contact_info.get("respondent_organization"),
    )


def _get_contact_info_by_article_id(article_id: int) -> Optional[Dict[str, Any]]:
    """Hae yhteystiedot article_id:n perusteella news_contacts taulusta."""
    db_dsn = os.getenv("DATABASE_URL")

    try:
        with psycopg.connect(db_dsn) as conn:
            with conn.cursor() as cur:
                # Hae ensisijainen yhteystieto tälle artikkelille
                cur.execute(
                    """
                    SELECT name, title, organization
                    FROM news_contacts
                    WHERE news_article_id = %s
                    ORDER BY id LIMIT 1
                    """,
                    (article_id,),
                )

                row = cur.fetchone()
                if not row:
                    return None

                name, title, organization = row
                print("CONTACT NAME:", name)
                print("CONTACT TITLE:", title)
                print("CONTACT ORGANIZATION:", organization)

                return {
                    "respondent_name": name or "Haastateltava",
                    "respondent_title": title,
                    "respondent_organization": organization,
                }

    except Exception as e:
        logger.error(f"Virhe haettaessa yhteystietoja article_id:llä: {e}")
        return None
