# schemas/parsed_article.py
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import List, Optional


# IF WE WANT TO DO INTERVIEWS, WE NEED TO STORE CONTACT INFORMATION
class NewsContact(BaseModel):
    """Contact information extracted from news articles."""

    name: Optional[str] = None
    title: Optional[str] = None
    organization: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    contact_type: str = "spokesperson"  # spokesperson, expert, decision_maker, etc.
    extraction_context: Optional[str] = None  # missä kohtaa tekstiä löytyi
    is_primary_contact: bool = False


# THIS IS PARSED ARTICLE
class ParsedArticle(BaseModel):
    """Simplified result from article parsing - only what we actually use."""

    markdown: str
    published: Optional[datetime] = None
    domain: Optional[str] = None
    url: Optional[str] = None
    contacts: List[NewsContact] = []
