from typing import List
from pydantic import (
    BaseModel,
    Field,
)

#THIS IS A SCHEMA FOR THE NEWS ARTICLE PLANNING AGENT
#WHICH ANALYZES A NEWS ARTICLE AND CREATES A PLAN TO ENRICH IT

class NewsArticlePlan(BaseModel):
    """A plan for enriching and expanding a news article."""

    article_id: str = Field(
        description="The unique identifier (URL) of the original article this plan is based on."
    )
    headline: str = Field(
        description="A new, interesting, and neutral headline based on the original article."
    )
    summary: str = Field(
        description="A concise, 1-2 sentence summary of the article's core message."
    )
    keywords: List[str] = Field(
        description="A list of 5-7 most important keywords describing the article's content."
    )
    categories: List[str] = Field(
        description="A list of the most important categories for the article (e.g., 'Technology', 'Politics', 'Sports')."
    )
    web_search_queries: List[str] = Field(
        description="A list of 2-3 specific, high-quality search queries to find additional information, different perspectives, or background details on the topic. The search queries must be in the same language as the original article."
    )
