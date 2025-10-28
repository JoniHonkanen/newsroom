# api/admin/test_article.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging
import os
from langchain.chat_models import init_chat_model

from agents.editor_in_chief_agent import EditorInChiefAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle

router = APIRouter()
logger = logging.getLogger(__name__)

class SimpleArticleTest(BaseModel):
    title: str = "Testiotsikko"
    content: Optional[str] = None
    article: Optional[str] = None
    
    def get_article_content(self) -> str:
        return self.content or self.article or ""
    
    def __init__(self, **data):
        super().__init__(**data)
        if not self.content and not self.article:
            raise ValueError("Either 'content' or 'article' field is required")

class TestArticleResponse(BaseModel):
    status: str
    editorial_decision: str
    featured: bool
    interview_needed: bool
    issues_count: int
    reasoning: str
    message: str
    review: Optional[Dict[str, Any]] = None
    prompt_used: Optional[str] = None
    model: Optional[str] = None

@router.post("/test-article-simple", response_model=TestArticleResponse)
async def test_article_simple(request: SimpleArticleTest):
    """Testaa artikkelia EditorInChiefAgent:illa"""
    try:
        model_name = "gpt-4o-mini"
        llm = init_chat_model(model_name, model_provider="openai")
        content = request.get_article_content()

        # Luo test article
        test_article = EnrichedArticle(
            article_id="test-simple",
            canonical_news_id=999,
            news_article_id=999,
            enriched_title=request.title,
            enriched_content=content,
            published_at="2024-01-01T10:00:00Z",
            source_domain="test.fi",
            keywords=[],
            categories=["Yleinen"],
            language="fi",
            sources=["https://test.fi/original"],
            references=[],
            locations=[],
            summary=(content[:200] + "..." if len(content) > 200 else content),
            enrichment_status="success",
            original_article_type="news",
            contacts=[],
        )

        initial_state = AgentState(
            current_article=test_article,
            enriched_articles=[test_article],
            reviewed_articles=[],
            review_result=None,
        )

        # Käytä OIKEAA tietokantaa (hakee persoonan)
        # Toimii sekä tuotannossa että kehityksessä
        DATABASE_URL = f"postgresql://{os.getenv('DB_USER', 'news')}:{os.getenv('DB_PASSWORD', 'news')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'newsroom')}"
        
        # Mock editorial service (ei tallenna reviewia tietokantaan)
        class MockEditorialReviewService:
            def __init__(self, db_dsn): 
                self.db_dsn = db_dsn
                logger.info("🎭 MockEditorialReviewService initialized (test mode)")
            
            def save_review(self, news_article_id, review_result): 
                logger.info(f"🎭 TEST MODE: Skipping database save for test article (id={news_article_id})")
                logger.info(f"   Status: {review_result.status}")
                logger.info(f"   Decision: {getattr(review_result, 'editorial_decision', 'N/A')}")
                return True

        try:
            # Luo EditorInChiefAgent normaalisti
            # Se hakee persoonan tietokannasta _get_active_persona_prompt() metodilla
            editor_agent = EditorInChiefAgent(llm, DATABASE_URL)
            
            # Vaihda VAIN editorial service mockiksi (ei tallenna tietokantaan)
            editor_agent.editorial_service = MockEditorialReviewService(DATABASE_URL)
            
            # Aja arviointi
            result_state = editor_agent.run(initial_state)

            review = getattr(result_state, "review_result", None)
            if review:
                review_dict = review.model_dump() if hasattr(review, 'model_dump') else {}

                featured = bool(getattr(getattr(review, "headline_news_assessment", None), "featured", False))
                interview_needed = bool(getattr(getattr(review, "interview_decision", None), "interview_needed", False))
                issues_count = len(getattr(review, "issues", []) or [])
                er = getattr(review, "editorial_reasoning", None)
                reasoning = getattr(er, "explanation", None) or "Ei perusteluja"
                decision = getattr(review, "editorial_decision", "unknown")

                return TestArticleResponse(
                    status="success",
                    editorial_decision=decision,
                    featured=featured,
                    interview_needed=interview_needed,
                    issues_count=issues_count,
                    reasoning=reasoning,
                    message="Arviointi valmis",
                    review=review_dict,
                    prompt_used=getattr(editor_agent, "active_prompt", None),
                    model=model_name,
                )
            else:
                logger.warning("No review_result in state after editor run")
                return TestArticleResponse(
                    status="error",
                    editorial_decision="unknown",
                    featured=False,
                    interview_needed=False,
                    issues_count=0,
                    reasoning="Ei tulosta",
                    message="Arviointi epäonnistui - ei review_result",
                )

        except Exception as e:
            logger.error(f"Error during editor agent run: {str(e)}", exc_info=True)
            return TestArticleResponse(
                status="error",
                editorial_decision="error",
                featured=False,
                interview_needed=False,
                issues_count=0,
                reasoning=f"Virhe agentin ajossa: {str(e)}",
                message="Tekninen virhe agentissa",
            )

    except Exception as e:
        logger.error(f"Virhe artikkeliarviossa: {str(e)}", exc_info=True)
        return TestArticleResponse(
            status="error",
            editorial_decision="error",
            featured=False,
            interview_needed=False,
            issues_count=0,
            reasoning=f"Virhe: {str(e)}",
            message="Tekninen virhe",
        )