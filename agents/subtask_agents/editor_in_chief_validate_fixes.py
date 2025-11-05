import sys
import os

# Lisätään projektin juurihakemisto polkuihin, jotta importit toimivat
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

# Tuodaan tarvittavat skeemat ja perusluokat OIKEISTA SIJAINNEISTA
from pydantic import BaseModel, Field
from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle
from schemas.editor_in_chief_schema import (
    ReviewedNewsItem,
    ReviewIssue,
    EditorialReasoning,
    HeadlineNewsAssessment,
    InterviewDecision,
)


# --- Yksinkertainen Pydantic-malli validoinnin tulokselle ---
class ValidationResult(BaseModel):
    """Represents the outcome of validating fixes."""

    all_fixes_verified: bool = Field(
        description="True if all required fixes have been successfully implemented."
    )
    remaining_issues: list[str] = Field(
        default=[],
        description="A list of descriptions for issues that were NOT properly fixed.",
    )
    verification_summary: str = Field(
        description="A brief summary explaining the validation decision."
    )


# --- Kohdennettu promptti validoinnille ---
FIX_VALIDATION_PROMPT = """
You are a meticulous Editorial Assistant responsible for verifying revisions.
An article was sent back for corrections based on a list of issues. A junior journalist has submitted a revised version.

Your **only task** is to check if the specific, required corrections have been made.
Do not perform a full new review. Do not look for new types of errors.
Focus exclusively on the requested changes.

Compare the "Required Corrections" with the "Revised Article" and determine if each point has been addressed.

## REQUIRED CORRECTIONS:
{issues_list}

---

## REVISED ARTICLE:

**Title:** {revised_title}

**Content:**
{revised_content}

---

## VERIFICATION:
Based on your comparison, are all the required corrections implemented?
Provide a clear summary of your findings and list any issues that still remain.
"""


class FixValidationAgent(BaseAgent):
    """
    An agent that validates if required fixes have been made to an article.
    It always produces a ReviewedNewsItem object containing the final editorial decision
    to guide the graph's conditional routing.
    """

    def __init__(self, llm):
        super().__init__(
            llm=llm, prompt=FIX_VALIDATION_PROMPT, name="FixValidationAgent"
        )
        self.structured_llm = self.llm.with_structured_output(ValidationResult)

    def _format_issues_list(self, issues: list[ReviewIssue]) -> str:
        """Formats the list of issues for the validation prompt."""
        if not issues:
            return "No specific issues were provided."

        formatted_issues = []
        for i, issue in enumerate(issues, 1):
            formatted_issues.append(
                f"{i}. **Type:** {issue.type}\n"
                f"   **Location:** {issue.location}\n"
                f"   **Problem:** {issue.description}\n"
                f"   **Suggestion:** {issue.suggestion}"
            )
        return "\n\n".join(formatted_issues)

    def run(self, state: AgentState) -> AgentState:
        """Runs the fix validation process and updates state.review_result with a decision."""
        print("🕵️  Running FixValidationAgent...")

        if not state.current_article or not state.review_result:
            print(
                "❌ FixValidationAgent: Missing current_article or review_result in state."
            )
            return state

        article: EnrichedArticle = state.current_article
        previous_review: ReviewedNewsItem = state.review_result

        # KRIITTINEN TARKISTUS: Hylkää automaattisesti jos liian monta revisiota
        if article.revision_count >= 2:
            print(
                f"⚠️ AUTOMATIC REJECTION: Article has been revised {article.revision_count} times. Maximum allowed is 2."
            )

            rejection_review = ReviewedNewsItem(
                status="ISSUES_FOUND",
                editorial_decision="reject",
                issues=[],
                editorial_reasoning=EditorialReasoning(
                    reviewer="FixValidationAgent",
                    initial_decision="REJECT",
                    explanation=f"Article automatically rejected after {article.revision_count} revisions. Maximum revision limit exceeded.",
                    checked_criteria=["Revision Count"],
                    failed_criteria=["Revision Count"],
                    reasoning_steps=[],
                ),
                headline_news_assessment=previous_review.headline_news_assessment
                or HeadlineNewsAssessment(
                    featured=False, reasoning="Rejected due to excessive revisions."
                ),
                interview_decision=previous_review.interview_decision
                or InterviewDecision(
                    interview_needed=False,
                    interview_method=None,  # ← KORJATTU: None eikä "none"
                    target_expertise_areas=[],
                    interview_focus=None,  # ← KORJATTU: None eikä "N/A"
                    justification="Article rejected.",
                    article_type_influence=None,  # ← KORJATTU: None eikä "N/A"
                ),
            )

            state.review_result = rejection_review
            print("🚫 Automatic rejection complete. Exiting validation immediately.")
            return state

        # Tarkista onko spesifisiä issues tai epäonnistuneita kriteerejä
        has_specific_issues = bool(previous_review.issues)
        has_failed_criteria = bool(
            previous_review.editorial_reasoning
            and previous_review.editorial_reasoning.failed_criteria
        )

        if not has_specific_issues and not has_failed_criteria:
            print("✅ No issues or failed criteria. Skipping validation.")
            # Varmistetaan, että päätös on olemassa reititystä varten
            if not state.review_result.editorial_decision:
                state.review_result.editorial_decision = "publish"
            return state

        # Jos on epäonnistuneita kriteerejä mutta ei spesifisiä issueita
        if has_failed_criteria and not has_specific_issues:
            print(
                f"⚠️ Article failed criteria: {previous_review.editorial_reasoning.failed_criteria}"
            )

            # Anna vielä yksi mahdollisuus jos ei ole maksimi revisiomäärää
            print("➡️ Allowing one more revision attempt for failed criteria.")

            # Luo uusi issue lista epäonnistuneista kriteereistä
            criteria_issues = [
                ReviewIssue(
                    type="Other",
                    location="Article",
                    description=f"Failed criteria: {criterion}",
                    suggestion=f"Please address the issues related to {criterion} to meet editorial standards.",
                )
                for criterion in previous_review.editorial_reasoning.failed_criteria
            ]

            # Päivitä review_result uusilla issueilla
            state.review_result.issues = criteria_issues
            state.review_result.editorial_decision = "revise"
            state.review_result.status = "ISSUES_FOUND"

            return state

        # Alkuperäinen logiikka spesifisten issues käsittelylle
        if has_specific_issues:
            print(
                f"📄 Validating fixes for article: {article.enriched_title[:50]}... (Revision count: {article.revision_count})"
            )

            try:
                issues_list_str = self._format_issues_list(previous_review.issues)
                prompt_content = self.prompt.format(
                    issues_list=issues_list_str,
                    revised_title=article.enriched_title,
                    revised_content=article.enriched_content,
                )

                print("🤖 Asking LLM to validate fixes...")
                validation_result: ValidationResult = self.structured_llm.invoke(
                    prompt_content
                )

                print("\n--- VALIDATION RESULT ---")
                print(f"Summary: {validation_result.verification_summary}")

                if validation_result.all_fixes_verified:
                    print("✅ SUCCESS: All required fixes have been verified.")
                    # Eli jos oli aiemmin päätetty haastattelusta... niin haastatellaan jos artikkeli muuten kunnossa
                    if (
                        previous_review.interview_decision
                        and previous_review.interview_decision.interview_needed
                    ):
                        final_decision = "interview"
                        print("🎤 Fixes verified, but interview still needed")
                    else:
                        final_decision = "publish"
                        print("✅ Fixes verified, ready to publish")

                    success_review = ReviewedNewsItem(
                        status="OK",
                        editorial_decision=final_decision,
                        issues=[],
                        editorial_reasoning=EditorialReasoning(
                            reviewer="FixValidationAgent",
                            initial_decision="ACCEPT",
                            explanation="All fixes were verified successfully.",
                            checked_criteria=["Fix Verification"],
                            failed_criteria=[],
                            reasoning_steps=[],
                        ),
                        headline_news_assessment=previous_review.headline_news_assessment,
                        editorial_warning=previous_review.editorial_warning,
                        interview_decision=previous_review.interview_decision,
                    )
                    state.review_result = success_review

                else:
                    print("❌ FAILED: Some issues remain.")

                    # Luo uusi issue lista jäljellä olevista ongelmista
                    new_issues_for_reviser = [
                        ReviewIssue(
                            type="Other",
                            location="Article",
                            description=issue_desc,
                            suggestion="Please fix this remaining issue based on the original feedback.",
                        )
                        for issue_desc in validation_result.remaining_issues
                    ]

                    decision = "reject" if article.revision_count >= 2 else "revise"

                    new_review_for_next_round = ReviewedNewsItem(
                        status="ISSUES_FOUND",
                        editorial_decision=decision,
                        issues=new_issues_for_reviser,
                        editorial_reasoning=EditorialReasoning(
                            reviewer="FixValidationAgent",
                            initial_decision="REJECT",
                            explanation=f"Validation failed. {len(new_issues_for_reviser)} issues remain after revision {article.revision_count}.",
                            checked_criteria=["Fix Verification"],
                            failed_criteria=["Fix Verification"],
                            reasoning_steps=[],
                        ),
                        headline_news_assessment=previous_review.headline_news_assessment,
                        interview_decision=previous_review.interview_decision,
                    )

                    state.review_result = new_review_for_next_round

                    if decision == "reject":
                        print(
                            f"⚠️ REJECTED: Article has been revised {article.revision_count} times and still fails. Rejecting."
                        )
                    else:
                        print(
                            f"➡️ REVISE: Sending for another revision with {len(new_issues_for_reviser)} specific issue(s)."
                        )

                print("-------------------------\n")

            except Exception as e:
                print(f"❌ An error occurred during fix validation: {e}")
                # Virhetilanteessa luodaan hylkäävä review_result
                error_review = previous_review.model_copy(deep=True)
                error_review.editorial_decision = "reject"
                error_review.issues.append(
                    ReviewIssue(
                        type="Other",
                        location="Validation Process",
                        description=f"Error: {e}",
                        suggestion="Manual review required.",
                    )
                )
                state.review_result = error_review
                import traceback

                traceback.print_exc()

        return state
