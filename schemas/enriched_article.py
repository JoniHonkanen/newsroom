# File: schemas/enriched_article.py

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone

from schemas.parsed_article import NewsContact

# THIS IS WHAT WE WANT TO STORE IN THE DATABASE WHEN NEWS ARTICLE IS ENRICHED
# WE SEND TO LLM "LLMArticleOutput", WHICH IS THEN USED IN "EnrichedArticle"


class ArticleReference(BaseModel):
    title: str = Field(description="The title of the referenced article.")
    url: str = Field(description="The original URL of the referenced article.")


# Location tags
class LocationTag(BaseModel):
    continent: Optional[str] = Field(description="Continent, e.g., 'Asia', 'Europe'")
    country: Optional[str] = Field(description="Country, e.g., 'Finland'")
    region: Optional[str] = Field(description="Region or state, e.g., 'Pirkanmaa'")
    city: Optional[str] = Field(description="City or locality, e.g., 'Akaa'")


# THIS IS WHAT WE SEND FOR LLM
class LLMArticleOutput(BaseModel):
    """Simplified schema for LLM output only."""

    enriched_title: str = Field(
        description="A new, enriched headline based on the original article and web search results."
    )
    enriched_content: str = Field(
        description="The enriched content of the news article in markdown format. Include only the article text itself."
    )
    keywords: List[str] = Field(
        description="5-10 keywords describing the article content."
    )
    summary: str = Field(
        description="Brief summary (up to 300 chars) highlighting key points",
    )
    locations: List[LocationTag] = Field(
        default_factory=list,
        description="Geographic locations mentioned in the article.",
    )
    image_suggestions: List[str] = Field(
        default_factory=list,
        description="1-3 descriptive search terms for images that would fit this article",
    )


# THIS IS WHAT WE STORE IN DB --- we will enrich this with LLMArticleOutput
class EnrichedArticle(BaseModel):
    """A fully enriched news article that combines original content with web search results."""

    news_article_id: Optional[int] = (
        None  # Database ID after saving it (article_storer_agent will set this)
    )
    article_id: str = Field(
        description="The unique identifier (URL) of the original article this is based on."
    )
    canonical_news_id: Optional[int] = Field(
        default=None, description="The canonical_news_id from the database if known"
    )
    enriched_title: str = Field(
        description="A new, enriched headline based on the original article and web search results."
    )
    enriched_content: str = Field(
        description="The enriched content of the news article, combining original information with web search results."
    )
    published_at: str = Field(
        description="The original publication date of the article."
    )
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO format timestamp when this enriched article was generated",
    )
    source_domain: str = Field(
        description="The domain where the original article was published."
    )
    keywords: List[str] = Field(description="Keywords describing the article content.")
    categories: List[str] = Field(description="Categories the article belongs to.")
    language: str = Field(description="The language of the article.")
    sources: List[str] = Field(
        description="URLs of the sources used to enrich the article."
    )
    references: List[ArticleReference] = Field(
        default_factory=list,
        description="References to articles mentioned in the content.",
    )
    locations: List[LocationTag] = Field(
        default_factory=list,
        description="Geographic locations mentioned in the article.",
    )
    summary: str = Field(
        description="Summary (up to 300 chars) highlighting keywords, for meta description",
    )
    enrichment_status: str = Field(
        default="pending", description="Status of web search enrichment"
    )
    original_article_type: Optional[str] = Field(
        default=None,
        description="The original article type (e.g., news, press release) if known",
    )
    featured: bool = Field(
        default=False,
        description="Whether this article should be featured on the front page (set by EditorInChiefAgent)",
    )
    interview_needed: bool = Field(
        default=False,
        description="Whether an interview is needed for this article (set by EditorInChiefAgent)",
    )
    contacts: Optional[list[NewsContact]] = Field(
        default=None,
        description="List of contacts related to the article (from original article)",
    )
    required_corrections: bool = Field(  # if editor in chief want changes to article
        default=False,
        description="Whether this article has been corrected due to issues found in review",
    )
    revision_count: int = Field(  # how many times this been fixed...
        default=0, description="Number of times this article has been revised"
    )
    hero_image_url: Optional[str] = Field(
        default=None, description="URL for the hero image of the article"
    )
    image_suggestions: List[str] = Field(
        default_factory=list, description="LLM suggested image search terms"
    )


# AFTER INTERVIEW, WE NEED TO ENRICH ARTICLE WITH INTERVIEW CONTENT
class EnrichedArticleWithInterview(BaseModel):
    """A fully enriched news article that combines original content with interview insights."""

    enriched_title: str = Field(description="A new, enriched headline")
    enriched_content: str = Field(
        description="The enriched content of the news article, combining original article information with interview insights."
    )
    summary: str = Field(
        description="Summary (up to 300 chars) highlighting keywords, for meta description",
    )
