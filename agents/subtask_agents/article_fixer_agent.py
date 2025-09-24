from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle
from schemas.editor_in_chief_schema import ReviewedNewsItem
from services.news_article_service import NewsArticleService


REVISION_PROMPT = """
You are an experienced journalist who revises articles based on editor-in-chief feedback.

You have been given:
1. Original article
2. Issues and correction suggestions found by the editor-in-chief
3. Additional editorial context (interviews needed, reconsiderations, warnings)

Your task is to revise the article so that it passes the editor-in-chief review on the next round.

## ORIGINAL ARTICLE:

**Title:** {original_title}

**Content:**
{original_content}

## EDITOR-IN-CHIEF FEEDBACK:

**Status:** {review_status}

**Issues found:**
{issues_list}

**General feedback:**
{general_feedback}

**Additional editorial context:**
{review_context}

### REVISION STRATEGY:

1. **Analyze severity:** Prioritize CRITICAL issues first
2. **For serious accusations:** 
   - Add phrases like "according to [source]", "alleged by [group]"
   - Include responses from accused parties if available
   - Use conditional language: "if true", "allegations suggest"
3. **Balance perspective:** Add opposing viewpoints, expert opinions, official statements
4. **Verify claims:** Only keep verifiable facts with credible sources
5. **Preserve core story:** Keep the newsworthy elements while fixing issues
6. **Maintain format:** Use same markdown structure as original

### SPECIAL HANDLING:
- If interview requirements are specified, note what additional sources are needed
- If reconsideration shows fundamental flaws, consider major restructuring
- If editorial warnings exist, address sensitive topic handling carefully

## REVISED ARTICLE:

Produce a revised version that addresses all critical issues while maintaining journalistic integrity.

**Title:** [Revised title - more neutral if needed]

**Content:**
[Revised content in markdown format - with balanced perspective and proper attribution]

**Summary of revisions:**
- [List the main changes made, especially for critical issues]
- [Note any fundamental restructuring]
- [Indicate if additional sources/interviews are still needed]
"""


class ArticleFixerAgent(BaseAgent):
    """Agent that revises articles based on editor-in-chief feedback."""
    
    #TODO:: reconsideration... sama kuin päätoimittajalla

    def __init__(self, llm, db_dsn: str):
        super().__init__(llm=llm, prompt=REVISION_PROMPT, name="ArticleFixerAgent")
        self.article_service = NewsArticleService(db_dsn=db_dsn)

    def _format_issues_list(self, issues) -> str:
        """Format issues list for the prompt."""
        if not issues:
            return "No specific issues found."

        formatted_issues = []
        for i, issue in enumerate(issues, 1):
            # Add severity indicator based on issue type
            severity = "CRITICAL" if issue.type in ["Legal", "Ethics"] else "MODERATE"

            formatted_issues.append(
                f"""
{i}. {severity} **{issue.type.upper()}** - {issue.location}
   Issue: {issue.description}
   Suggestion: {issue.suggestion}
"""
            )
        return "\n".join(formatted_issues)

    def _format_review_context(self, review) -> str:
        """Format additional review context like reconsideration and interview needs."""
        context_parts = []

        # Add interview decision if needed
        if (
            hasattr(review, "interview_decision")
            and review.interview_decision.interview_needed
        ):
            interview = review.interview_decision
            context_parts.append(
                f"""
**INTERVIEW REQUIREMENTS:**
- Method: {interview.interview_method or 'Not specified'}
- Target expertise: {', '.join(interview.target_expertise_areas) if interview.target_expertise_areas else 'Not specified'}
- Focus: {interview.interview_focus or 'Not specified'}
- Justification: {interview.justification}
"""
            )

        # Add reconsideration details if present
        if hasattr(review, "reconsideration") and review.reconsideration:
            recon = review.reconsideration
            context_parts.append(
                f"""
**RECONSIDERATION ANALYSIS:**
- Final decision: {recon.final_decision}
- Critical issues: {', '.join(recon.failed_criteria)}
- Editor's final assessment: {recon.explanation}
"""
            )

        # Add editorial warning if present
        if hasattr(review, "editorial_warning") and review.editorial_warning:
            warning = review.editorial_warning
            context_parts.append(
                f"""
**EDITORIAL WARNING ISSUED:**
- Category: {warning.category}
- Details: {warning.details}
- Sensitive topics: {', '.join(warning.topics) if warning.topics else 'None specified'}
"""
            )

        return (
            "\n".join(context_parts)
            if context_parts
            else "No additional editorial context."
        )

    def _extract_corrected_content(self, llm_response: str) -> tuple[str, str]:
        """Extract title and content from LLM response."""
        lines = llm_response.strip().split("\n")

        title = ""
        content_lines = []
        in_content = False

        for line in lines:
            # Look for title
            if line.startswith("**Title:**"):
                title = line.replace("**Title:**", "").strip()
            # Look for content start
            elif line.startswith("**Content:**"):
                in_content = True
                continue
            # Stop at summary
            elif line.startswith("**Summary of revisions:**"):
                break
            # Collect content lines
            elif in_content:
                content_lines.append(line)

        content = "\n".join(content_lines).strip()

        # Fallback if extraction fails
        if not title or not content:
            print(
                "⚠️ Failed to extract title/content properly, using original structure"
            )
            # Try simpler extraction
            if "**Title:**" in llm_response:
                parts = llm_response.split("**Title:**", 1)[1]
                if "**Content:**" in parts:
                    title_part, content_part = parts.split("**Content:**", 1)
                    title = title_part.strip()
                    if "**Summary of revisions:**" in content_part:
                        content = content_part.split("**Summary of revisions:**")[
                            0
                        ].strip()
                    else:
                        content = content_part.strip()

        return title, content

    def run(self, state: AgentState) -> AgentState:
        """Revise the current article based on editor feedback."""

        if not hasattr(state, "current_article") or not state.current_article:
            print("❌ ArticleFixerAgent: No current_article to revise!")
            return state

        if not hasattr(state, "review_result") or not state.review_result:
            print("❌ ArticleFixerAgent: No review_result found!")
            return state

        article: EnrichedArticle = state.current_article
        review = state.review_result

        print(
            f"🔧 Revising article: {getattr(article, 'enriched_title', 'Unknown')[:50]}..."
        )
        print(f"📋 Found {len(review.issues)} issues to fix")
        print("TÄÄ ON SE MIKÄ KIINNOSTAA!!!!!")
        print(review)

        try:
            # Format the issues for the prompt
            issues_list = self._format_issues_list(review.issues)

            # Get general feedback from reasoning
            general_feedback = getattr(
                review.editorial_reasoning, "explanation", "See detailed issues above."
            )

            # Format additional review context (interviews, reconsideration, warnings)
            review_context = self._format_review_context(review)

            # Prepare prompt
            prompt_content = self.prompt.format(
                original_title=getattr(article, "enriched_title", ""),
                original_content=getattr(article, "enriched_content", ""),
                review_status=review.status,
                issues_list=issues_list,
                general_feedback=general_feedback,
                review_context=review_context,
            )

            # Get revision from LLM
            print("🤖 Generating revised version...")
            llm_response = self.llm.invoke(prompt_content).content

            # Extract revised title and content
            corrected_title, corrected_content = self._extract_corrected_content(
                llm_response
            )

            if not corrected_title or not corrected_content:
                print("❌ Failed to extract revised content from LLM response")
                print("📝 LLM Response preview:", llm_response[:200] + "...")
                return state

            # Update the article with revised content
            article.enriched_title = corrected_title
            article.enriched_content = corrected_content

            # Update correction tracking fields
            article.required_corrections = True
            article.revision_count += 1

            print(f"✅ Article revised successfully!")
            print(f"📝 New title: {corrected_title[:50]}...")
            print(article.enriched_content)

            # Update in database if article has been stored
            if article.news_article_id:

                success = self.article_service.update_enriched_article(article)
                if success:
                    print(
                        f"✅ Updated article in database (ID: {article.news_article_id})"
                    )
                else:
                    print(f"⚠️ Failed to update article in database")
            else:
                print("⚠️ Article not yet in database, skipping DB update")

                # Show excerpt of changes
                if len(corrected_content) > 100:
                    print(f"📋 Content preview: {corrected_content[:100]}...")

        except Exception as e:
            print(f"❌ Error during revision: {e}")
            import traceback

            traceback.print_exc()

        return state


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    from langchain.chat_models import init_chat_model
    from schemas.enriched_article import EnrichedArticle, ArticleReference, LocationTag
    from schemas.agent_state import AgentState
    from schemas.editor_in_chief_schema import (
        ReviewedNewsItem,
        ReviewIssue,
        EditorialReasoning,
        HeadlineNewsAssessment,
        InterviewDecision,
        ReasoningStep,
        EditorialWarning,
        Reconsideration,
    )
    from typing import Any
    import os
    
    # Run this script to test the ArticleFixerAgent without a real database connection.
    # Command: python -m agents.subtask_agents.article_fixer_agent

    print("--- Running ArticleFixerAgent WITHOUT Database (MOCK) ---")
    load_dotenv()

    # Initialize LLM
    try:
        llm = init_chat_model("gpt-4o-mini", model_provider="openai")
        print("✅ LLM initialized successfully")
    except Exception as e:
        print(f"❌ Error initializing LLM: {e}")
        sys.exit(1)

    # Mock database service - we wont be saving anything to a real database
    class MockNewsArticleService:
        """Mock service that doesn't actually connect to database"""

        def __init__(self, db_dsn):
            print(f"🎭 MockNewsArticleService initialized (no real database)")
            self.db_dsn = db_dsn

        def update_enriched_article(self, article):
            print(f"🎭 MOCK UPDATE: Would update article ID {article.news_article_id}")
            print(f"     New title: {article.enriched_title[:50]}...")
            print(f"     Content length: {len(article.enriched_content)} chars")
            print(f"     Revision count: {getattr(article, 'revision_count', 0)}")
            return True  # Always successful

    # Patch ArticleFixerAgent to use mock
    def mock_init(self, llm, db_dsn: str = None):
        super(ArticleFixerAgent, self).__init__(
            llm=llm, prompt=REVISION_PROMPT, name="ArticleFixerAgent"
        )
        self.article_service = MockNewsArticleService(db_dsn or "mock://db")

    ArticleFixerAgent.__init__ = mock_init

    # Create test article with issues that need fixing
    test_article = EnrichedArticle(
        article_id="test-article-needs-fixing",
        canonical_news_id=456,
        news_article_id=2,  # Has database ID
        enriched_title="Kiistanalainen päätös: Hallitus nostaa veroja dramaattisesti",
        enriched_content="""
# Kiistanalainen päätös: Hallitus nostaa veroja dramaattisesti

Hallitus päätti tänään nostaa veroja merkittävästi ilman kunnollista perustelua. Päätös on saanut laajaa kritiikkiä kansalaisilta.

## Vastustus kasvaa

Monet ihmiset ovat tyytymättömiä tähän päätökseen. Opposition johtaja sanoi päätöksen olevan "täysin järjetön".

## Epäselvä tulevaisuus

Pääministeri ei kommentoinut asiaa lainkaan, mikä herättää epäilyksiä hallituksen avoimuudesta.

Veronkorotukset tulevat voimaan heti.
        """.strip(),
        published_at="2024-01-15T10:00:00Z",
        generated_at="2024-01-15T12:00:00Z",
        source_domain="test.fi",
        keywords=["hallitus", "verot", "politiikka"],
        categories=["Politiikka"],
        language="fi",
        sources=["https://example.com/government-decision"],
        references=[
            ArticleReference(
                title="Hallituksen tiedote", url="https://government.fi/taxes"
            )
        ],
        locations=[LocationTag(continent="Europe", region="Southern Finland", country="Finland", city="Helsinki")],
        summary="Hallitus päätti nostaa veroja, päätös saanut kritiikkiä.",
        enrichment_status="success",
        original_article_type="news",
        contacts=[],
        # Initialize revision tracking
        required_corrections=False,
        revision_count=0,
    )

    # Create comprehensive review with multiple types of issues
    test_review = ReviewedNewsItem(
        status="ISSUES_FOUND",
        editorial_decision="revise",
        issues=[
            ReviewIssue(
                type="Legal",
                location="Otsikko ja ensimmäinen kappale",
                description="Sana 'kiistanalainen' ja 'dramaattisesti' ovat liian subjektiivisia uutisessa. Voi antaa harhaanjohtavan kuvan.",
                suggestion="Käytä neutraalia kieltä: 'Hallitus päätti nostaa veroja' ilman arvottavia adjektiiveja",
            ),
            ReviewIssue(
                type="Accuracy",
                location="Toinen kappale",
                description="Väite 'ilman kunnollista perustelua' ei ole faktuaalinen - hallitus on antanut perusteluja",
                suggestion="Lisää hallituksen perustelut tai poista väittämä",
            ),
            ReviewIssue(
                type="Ethics",
                location="Opposition johtajan lainaus",
                description="Lainaus 'täysin järjetön' ilman kontekstia tai vastinetta voi olla epätasapuolinen",
                suggestion="Lisää hallituksen vastine tai opposition johtajan täydellinen kommentti kontekstissa",
            ),
            ReviewIssue(
                type="Style",
                location="Koko artikkeli",
                description="Artikkeli on liian lyhyt ja puutteellinen tärkeässä aiheessa",
                suggestion="Lisää yksityiskohtia: mitä veroja, kuinka paljon, milloin, miksi",
            ),
            ReviewIssue(
                type="Accuracy",
                location="Viimeinen lause",
                description="'Veronkorotukset tulevat voimaan heti' - tarkista onko tämä faktaa",
                suggestion="Tarkista toteutusaikataulu ja korjaa jos tarpeellista",
            ),
        ],
        editorial_reasoning=EditorialReasoning(
            reviewer="EditorInChiefAgent",
            initial_decision="REJECT",
            checked_criteria=[
                "Legal Compliance",
                "Accuracy",
                "Ethics",
                "Style",
                "Balance",
            ],
            failed_criteria=["Legal Compliance", "Accuracy", "Ethics", "Style"],
            reasoning_steps=[
                ReasoningStep(
                    step_id=1,
                    action="Check neutrality",
                    observation="Found subjective language in headline and content",
                    result="FAIL",
                ),
                ReasoningStep(
                    step_id=2,
                    action="Verify facts",
                    observation="Some claims appear unsubstantiated",
                    result="FAIL",
                ),
                ReasoningStep(
                    step_id=3,
                    action="Check balance",
                    observation="Article lacks government perspective",
                    result="FAIL",
                ),
            ],
            explanation="Article has multiple issues with neutrality, accuracy and balance that need correction before publication",
        ),
        headline_news_assessment=HeadlineNewsAssessment(
            featured=False,
            reasoning="Important topic but article quality issues prevent featuring",
        ),
        interview_decision=InterviewDecision(
            interview_needed=True,
            interview_method="email",
            target_expertise_areas=["tax policy", "government communications"],
            interview_focus="Get official government response and expert analysis on tax policy",
            justification="Article needs government perspective and expert context for balance",
            article_type_influence="Government policy announcement requires official response",
        ),
        editorial_warning=EditorialWarning(
            category="SensitiveTopic",
            details="Tax policy is politically sensitive - ensure balanced reporting",
            topics=["taxation", "government policy", "political controversy"],
        ),
    )

    # Create AgentState with both article and review
    initial_state = AgentState(
        current_article=test_article,
        enriched_articles=[test_article],
        review_result=test_review,
        reviewed_articles=[],
    )

    print(f"\nTest Setup:")
    print(f"- Article: {test_article.enriched_title[:50]}...")
    print(f"- Review status: {test_review.status}")
    print(f"- Issues to fix: {len(test_review.issues)}")
    print(f"- Editorial decision: {test_review.editorial_decision}")
    print(f"- Interview needed: {test_review.interview_decision.interview_needed}")
    print(
        f"- Editorial warning: {test_review.editorial_warning.category if test_review.editorial_warning else 'None'}"
    )

    try:
        print(f"\n--- Creating ArticleFixerAgent (MOCK) ---")
        fixer_agent = ArticleFixerAgent(llm, "mock://database/connection")
        print(f"✅ Agent created with mock database")

        print(f"\n--- Running article revision ---")
        result_state = fixer_agent.run(initial_state)
        print(f"✅ Revision completed")

        # Display comprehensive results
        print(f"\n{'='*80}")
        print(f"🔧 ARTICLE REVISION RESULTS (MOCK DATABASE)")
        print(f"{'='*80}")

        if hasattr(result_state, "current_article") and result_state.current_article:
            revised_article = result_state.current_article

            print(f"\n📝 BEFORE vs AFTER:")
            print(f"   Original Title: {test_article.enriched_title}")
            print(f"   Revised Title:  {revised_article.enriched_title}")
            print(
                f"   Title Changed:  {'✅ YES' if test_article.enriched_title != revised_article.enriched_title else '❌ NO'}"
            )

            print(f"\n📊 CONTENT COMPARISON:")
            original_length = len(test_article.enriched_content)
            revised_length = len(revised_article.enriched_content)
            print(f"   Original Length: {original_length} characters")
            print(f"   Revised Length:  {revised_length} characters")
            print(
                f"   Length Change:   {revised_length - original_length:+d} characters"
            )

            print(f"\n📋 REVISION TRACKING:")
            print(
                f"   Required Corrections: {getattr(revised_article, 'required_corrections', 'Not set')}"
            )
            print(
                f"   Revision Count: {getattr(revised_article, 'revision_count', 'Not set')}"
            )

            print(f"\n📄 REVISED CONTENT PREVIEW:")
            content_preview = revised_article.enriched_content[:300]
            print(f"   {content_preview}...")
            if len(revised_article.enriched_content) > 300:
                print(
                    f"   ... and {len(revised_article.enriched_content) - 300} more characters"
                )

            # Check for specific improvements
            print(f"\n🔍 IMPROVEMENT ANALYSIS:")
            original_words = test_article.enriched_content.lower()
            revised_words = revised_article.enriched_content.lower()

            improvements = []
            if "kiistanalainen" not in revised_article.enriched_title.lower():
                improvements.append("✅ Removed subjective language from title")
            if "dramaattisesti" not in revised_words:
                improvements.append("✅ Removed dramatic language")
            if (
                len(revised_article.enriched_content)
                > len(test_article.enriched_content) * 1.2
            ):
                improvements.append("✅ Significantly expanded content")
            if "hallituksen mukaan" in revised_words or "ministeri" in revised_words:
                improvements.append("✅ Added government perspective")

            if improvements:
                for improvement in improvements:
                    print(f"   {improvement}")
            else:
                print(f"   ⚠️  No obvious improvements detected")

            # Success metrics
            print(f"\nTEST METRICS:")
            print(f"LLM revision call: SUCCESS")
            print(
                f"Content extraction: {'SUCCESS' if revised_article.enriched_content else 'FAIL'}"
            )
            print(
                f"Title extraction: {'SUCCESS' if revised_article.enriched_title else 'FAIL'}"
            )
            print(f"Database update: MOCKED")
            print(
                f"Article structure: {'SUCCESS' if '# ' in revised_article.enriched_content else 'PARTIAL'}"
            )

        else:
            print(f"❌ NO REVISED ARTICLE FOUND")

        print(f"\n✅ Test completed successfully WITHOUT database!")
        print(f"🎭 All database operations were mocked")
        print(
            f"The agent successfully processed {len(test_review.issues)} editorial issues"
        )

    except Exception as e:
        print(f"\n❌ ERROR IN TEST: {e}")
        import traceback

        print(f"\nFull traceback:")
        traceback.print_exc()

        print(f"\n🔧 TROUBLESHOOTING:")
        print(f"   1. Check OPENAI_API_KEY in .env")
        print(f"   2. Verify LLM response parsing in _extract_corrected_content()")
        print(f"   3. Check that revision prompt produces expected format")

# Agent flow (before and after):
# ... -> editor_in_chief_agent -> ARTICLE_FIXER_AGENT (WE ARE HERE) -> editor_in_chief_validate_fixes -> ...
