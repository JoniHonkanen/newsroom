# Editorial Review Schemas
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class ReasoningStep(BaseModel):
    step_id: int = Field(description="Sequential number of the reasoning step")
    action: str = Field(
        description="Action performed in this step (e.g., 'Evaluate Accuracy')"
    )
    observation: str = Field(description="What was observed during this step")
    result: Literal["PASS", "FAIL", "INFO"] = Field(description="Outcome of this step")


class Reconsideration(BaseModel):
    failed_criteria: List[str] = Field(
        description="List of criteria initially failed but considered for final reassessment"
    )
    final_decision: Literal["ACCEPT", "REJECT"] = Field(
        description="Final editorial decision after reconsideration"
    )
    reasoning_steps: List[ReasoningStep] = Field(
        default_factory=list,
        description="Additional steps taken during the reconsideration process",
    )
    explanation: str = Field(
        description="Explanation for why the final decision was made, considering all factors"
    )


class EditorialWarning(BaseModel):
    category: Literal[
        "SensitiveTopic", "MinorityGroup", "Religion", "Violence", "Other"
    ] = Field(description="Primary reason for issuing an editorial warning")
    details: str = Field(
        description="Free-form explanation shown to readers (why the topic is sensitive)"
    )
    topics: List[str] = Field(
        default_factory=list,
        description="Specific topics or keywords that triggered the reconsideration",
    )


class HeadlineNewsAssessment(BaseModel):
    """Assessment of whether the article deserves featured placement."""

    featured: bool = Field(
        description="Whether this article should be featured on the front page"
    )

    reasoning: str = Field(
        description="Detailed explanation of the featured placement decision"
    )


class EditorialReasoning(BaseModel):
    reviewer: str = Field(description="Identifier of the editor agent")
    initial_decision: Literal["ACCEPT", "REJECT"] = Field(
        description="Initial high-level verdict"
    )
    checked_criteria: List[str] = Field(description="All evaluated review criteria")
    failed_criteria: List[str] = Field(
        description="Subset of checked criteria that did not pass"
    )
    reasoning_steps: List[ReasoningStep] = Field(
        default_factory=list,
        description="Detailed reasoning steps for the initial decision",
    )
    explanation: str = Field(
        description="Narrative tying the evaluation results to the initial decision"
    )
    reconsideration: Optional[Reconsideration] = Field(
        default=None, description="Optional reconsideration after the initial decision"
    )


class ReviewIssue(BaseModel):
    type: Literal["Legal", "Accuracy", "Ethics", "Style", "Other"] = Field(
        description="Category of the identified issue"
    )
    location: str = Field(description="Where the issue appears in the article")
    description: str = Field(description="Description of the issue")
    suggestion: str = Field(description="Suggested correction or improvement")


class InterviewDecision(BaseModel):
    interview_needed: bool
    interview_method: Optional[Literal["phone", "email"]] = None
    target_expertise_areas: List[str] = (
        []
    )  # Areas of expertise needed for the interview
    interview_focus: Optional[str] = None  # Specific topics to cover in the interview
    justification: Optional[str] = None  # Why we need an interview
    article_type_influence: Optional[str] = (
        None  # how the article type influences (press release, news...)
    )


class ReviewedNewsItem(BaseModel):
    status: Literal["OK", "ISSUES_FOUND", "RECONSIDERATION"] = Field(
        description="Overall editorial review outcome"
    )
    issues: List[ReviewIssue] = Field(
        default_factory=list, description="List of issues found during the review"
    )
    approval_comment: Optional[str] = Field(
        default=None,
        description="Comment explaining why the article was accepted (if applicable)",
    )
    editorial_reasoning: EditorialReasoning = Field(
        description="Editorial reasoning supporting the decision"
    )
    reconsideration: Optional[Reconsideration] = Field(
        default=None, description="Final reconsideration result, if applicable"
    )
    editorial_warning: Optional[EditorialWarning] = Field(
        description="Structured warning to readers; required if status is 'RECONSIDERATION'",
    )
    headline_news_assessment: HeadlineNewsAssessment = Field(
        description="Assessment of whether this article should be featured on the front page"
    )
    interview_decision: InterviewDecision = Field(
        description="Decision on whether interviews are needed for this article"
    )
    editorial_decision: Literal["publish", "interview", "revise", "reject"] = Field(
        description="Final editorial routing decision based on review"
    )
