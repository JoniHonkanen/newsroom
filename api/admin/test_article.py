# api/admin/test_article.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional

router = APIRouter()

class SimpleArticleTest(BaseModel):
    content: str
    title: str = "Testiotsikko"

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
    """Testaa artikkelia pelkällä tekstillä"""
    # TODO: Lisää testauslogiikka myöhemmin
    return TestArticleResponse(
        status="success",
        editorial_decision="publish",
        featured=False,
        interview_needed=False,
        issues_count=0,
        reasoning="Test response",
        message="Test completed"
    )