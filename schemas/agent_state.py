from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from schemas.article_plan_schema import NewsArticlePlan
from schemas.editor_in_chief_schema import ReviewedNewsItem
from schemas.enriched_article import EnrichedArticle, EnrichedArticleWithInterview
from schemas.feed_schema import CanonicalArticle
from schemas.interview_schema import InterviewPlan
from schemas.parsed_article import ParsedArticle

# Shared state between the agents


class AgentState(BaseModel):
    articles: List[CanonicalArticle] = Field(
        default_factory=list
    )  # ARTICLES FETCHED FROM THE FEED
    plan: List[NewsArticlePlan] = Field(default_factory=list)
    article_search_map: Dict[str, List[ParsedArticle]] = Field(default_factory=dict)
    canonical_ids: Dict[str, int] = Field(
        default_factory=dict
    )  # MAP OF ARTICLE URLS TO THEIR CANONICAL IDs
    enriched_articles: List[EnrichedArticle] = Field(
        default_factory=list
    )  # GENERATED & ENRICHED ARTICLES
    reviewed_articles: List[Any] = Field(
        default_factory=list
    )  # ARTICLES THAT HAVE BEEN REVIEWED BY THE EDITOR IN CHIEF
    # FOR PROCESSING FOLLOW-UPS - AFTER EDITOR IN CHIEF REVIEW
    current_article: Optional[Any] = None
    review_result: Optional[ReviewedNewsItem] = None
    pending_interviews: List[Any] = Field(default_factory=list)
    pending_revisions: List[Any] = Field(default_factory=list)
    interview_plan: Optional[InterviewPlan] = Field(default=None)

class InterviewAgentState(AgentState):
    current_article: Optional[Any] = None
    interview_content: Optional[str] = None
    new_enriched_article: Optional[EnrichedArticleWithInterview] = None
    interview_respondent_name: Optional[str] = None
    interview_respondent_title: Optional[str] = None
    interview_respondent_organization: Optional[str] = None
