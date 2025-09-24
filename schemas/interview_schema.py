from pydantic import BaseModel, Field
from typing import List, Optional, Literal

# OWN PLANS FOR INTERVIEWS - PHONE - EMAIL


class InterviewQuestion(BaseModel):
    """Single interview question with metadata"""

    topic: str = Field(description="Question topic area")
    question: str = Field(description="The actual question text")
    position: int = Field(description="Order position in interview")


class EmailInterviewPlan(BaseModel):
    """Email interview specific plan - maps to email_interview + email_questions tables"""

    news_article_id: int = Field(description="Links to news_article.id")
    interview_decision_id: Optional[int] = Field(
        default=None, description="Links to editorial_interview_decisions.id"
    )

    # Email-specific fields (for email_interview table)
    recipient: str = Field(description="Email address to send to")
    subject: str = Field(description="Email subject line")

    # Questions (for email_questions table) - 2-5 kysymystä
    questions: List[InterviewQuestion] = Field(
        description="Questions to include in email (2-5 questions recommended)"
    )

    # Context
    background_context: str = Field(description="Context/introduction for email")
    target_expertise_areas: List[str] = Field(description="From editorial decision")
    interview_focus: str = Field(description="From editorial decision")
    formatted_email_body: str = Field(
        description="Complete email with intro, questions, outro, and signature - ready to send"
    )


class PhoneInterviewPlan(BaseModel):
    """Phone interview plan - clean, no duplicates with interviewplan"""

    # Phone essentials
    to_number: str = Field(description="Phone number to call")
    from_number: Optional[str] = Field(default=None, description="Calling number")

    # Single source of truth
    phone_script_json: dict = Field(
        description="Complete phone interview script for Realtime API"
    )


class InterviewPlan(BaseModel):
    """Main interview plan - contains either email or phone plan"""

    # Core identifiers
    canonical_news_id: int = Field(description="Links to canonical_news.id")
    article_id: int = Field(description="Links to news_article.id")

    # Method determines which plan to use
    interview_method: Literal["phone", "email"] = Field(
        description="How to conduct interview"
    )

    # Method-specific plans (only one will be populated)
    email_plan: Optional[EmailInterviewPlan] = Field(
        default=None, description="Email interview details"
    )
    phone_plan: Optional[PhoneInterviewPlan] = Field(
        default=None, description="Phone interview details"
    )

    # Available contacts from article
    available_contacts: List = Field(
        description="NewsContact objects from parsed article"
    )  # Type hint kept loose to avoid circular imports


class DataAfterInterviewFromDatabase(BaseModel):
    """Data structure for storing information after an interview is conducted."""

    article_id: int = Field(description="Links to news_article.id")
    enriched_title: str = Field(description="The enriched title of the article")
    enriched_content: str = Field(description="The enriched content of the article")
    language: str = Field(description="The language of the article")
