from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel

from schemas.parsed_article import NewsContact


# For RSS feeds, we define categories to classify the type of news.
class FeedCategory(str, Enum):
    press_release = "press_release"
    news = "news"
    other = "other"


# THIS SCHEMA IS USED TO CONFIGURE RSS FEEDS...
# CURRENTLY newsfood.yaml. IS USED TO STORE THE FEED CONFIGURATIONS.
class NewsFeedConfig(BaseModel):
    name: str
    extra_info: str | None = None
    feed_type: str
    category: FeedCategory
    origin: str | None = None
    url: str
    active: bool = True
    added_at: str | None = None
    modified_at: str | None = None


# THIS IS USED TO KEEP TRACK OF THE STATE OF EACH FEED (RSS).
# SO AGENT KNOW WHICH FEEDS HAVE BEEN CHECKED AND PROCESSED, OR IF THE NEWS ARE NEW ONES
class FeedState(BaseModel):
    url: str
    last_modified: str | None = None
    etag: str | None = None
    updated: bool = False
    last_checked: str | None = None
    last_processed_id: str | None = None
    last_processed_published: str | None = None

# THIS IS SCHEMA FOR FETCHED ARTICLES FROM RSS FEEDS.
class CanonicalArticle(BaseModel):
    title: str
    link: str
    summary: Optional[str] = None
    unique_id: Optional[str] = None
    content: Optional[str] = None
    published_at: Optional[str] = None
    source_domain: Optional[str] = None  # esim yle.fi
    language: Optional[str] = None
    article_type: Optional[str] = None
    contacts: Optional[list[NewsContact]] = None  # List of contact information dictionaries
