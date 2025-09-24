# File: schemas/news_article_db.py

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


# THIS IS WHAT WE USE TO STORE GENERATED NEWS ARTICLES IN THE DATABASE
# LOOKS ALMOST SAME AS "EnrichedArticle" BUT WE HAVE SOME EXTRA FIELDS, e.g. "embedding" and "body_blocks"
class NewsArticleDB(BaseModel):
    """Database model for a news article matching the news_article table in enable_pgvector.sql."""

    id: Optional[int] = Field(default=None, description="Database ID (auto-generated)")
    canonical_news_id: int = Field(
        description="Reference to the ID in canonical_news table"
    )
    language: str = Field(description="ISO language code (e.g., 'fi', 'en', 'sv')")
    version: int = Field(default=1, description="Version number for tracking updates")
    lead: Optional[str] = Field(default=None, description="Article lead/introduction")
    summary: Optional[str] = Field(
        default=None, description="Brief summary of the article"
    )
    status: Optional[str] = Field(
        default=None, description="Publication status (draft, published, archived)"
    )
    location_tags: Optional[Dict[str, Any]] = Field(
        default=None, description="JSON structure of location information"
    )
    sources: Optional[List[Dict[str, str]]] = Field(
        default=None, description="JSON list of sources used in the article"
    )
    interviews: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="JSON list of interviews referenced in the article"
    )
    review_status: Optional[str] = Field(
        default=None, description="Status of the news (breaking, update, etc.)"
    )
    author: Optional[str] = Field(default=None, description="Author of the article")
    embedding: Optional[List[float]] = Field(
        default=None,
        description="Vector embedding of the article content for semantic search",
    )
    body_blocks: List[Dict[str, Any]] = Field(
        description="JSON structure of content blocks including HTML elements"
    )
    markdown_content: Optional[str] = Field(
        default=None, description="Original markdown content of the article as a whole"
    )
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = Field(
        default=None, description="Last update timestamp"
    )
    enrichment_status: Optional[str] = Field(
        default="pending", description="Status of the enrichment process"
    )
    original_article_type: Optional[str] = Field(
        default=None,
        description="The original article type (e.g., news, press release) if known",
    )
    hero_image_url: Optional[str] = Field(
        default=None,
        description="URL for the hero image of the article",
    )

    class Config:
        from_attributes = True  # For SQLAlchemy compatibility
