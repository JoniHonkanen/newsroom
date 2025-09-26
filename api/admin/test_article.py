# api/admin/test_article.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging
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

        # Mock editorial service (ei tallenna tietokantaan)
        class MockEditorialReviewService:
            def __init__(self, db_dsn): pass
            def save_review(self, news_article_id, review_result): return True

        # Käytä EditorInChiefAgent:ia
        DATABASE_URL = "postgresql://test:test@localhost:5432/test"  # Mock URL
        
        original_init = EditorInChiefAgent.__init__
        def mock_init(self, llm, db_dsn: str):
            from agents.base_agent import BaseAgent
            from schemas.editor_in_chief_schema import ReviewedNewsItem
            BaseAgent.__init__(self, llm=llm, prompt=None, name="EditorInChiefAgent")
            self.structured_llm = self.llm.with_structured_output(ReviewedNewsItem)
            self.db_dsn = db_dsn
            self.active_prompt = "Test prompt"  # Mock prompt
            self.editorial_service = MockEditorialReviewService(db_dsn)

        EditorInChiefAgent.__init__ = mock_init

        try:
            editor_agent = EditorInChiefAgent(llm, DATABASE_URL)
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

        finally:
            EditorInChiefAgent.__init__ = original_init

        return TestArticleResponse(
            status="error",
            editorial_decision="unknown",
            featured=False,
            interview_needed=False,
            issues_count=0,
            reasoning="Ei tulosta",
            message="Arviointi epäonnistui",
        )

    except Exception as e:
        logger.error(f"Virhe artikkeliarviossa: {str(e)}")
        return TestArticleResponse(
            status="error",
            editorial_decision="error",
            featured=False,
            interview_needed=False,
            issues_count=0,
            reasoning=f"Virhe: {str(e)}",
            message="Tekninen virhe",
        )