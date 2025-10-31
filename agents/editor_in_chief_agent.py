# File: agents/editor_in_chief_agent.py

import sys
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# Add the project root to the Python path FIRST
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

# Now import the modules
from schemas.editor_in_chief_schema import (
    EditorialReasoning,
    InterviewDecision,
    ReasoningStep,
    ReviewIssue,
    ReviewedNewsItem,
    HeadlineNewsAssessment,
)
from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle
from services.editor_review_service import EditorialReviewService


# We only do phone interviews between 08:00 and 18:00 Helsinki time... otherwise email only.
def is_phone_interview_time() -> bool:
    """
    Check if current time is within allowed phone interview hours (08:00-18:00 Helsinki time).
    Returns True if phone interviews are allowed, False otherwise.
    """
    helsinki_tz = ZoneInfo("Europe/Helsinki")
    current_time = datetime.now(helsinki_tz)
    current_hour = current_time.hour

    # Phone interviews allowed between 08:00 and 18:00
    return 8 <= current_hour < 18


# PROMPT WHEN PHONE INTERVIEWS ARE ALLOWED (08:00-18:00 Helsinki time)
EDITOR_IN_CHIEF_PROMPT_PHONE_ALLOWED = """
{persona}

Your task is to review the news article and verify that it complies with:
- Finnish journalistic law (Freedom of Expression Act, Criminal Code)
- JSN's Journalistin ohjeet (ethical code)
- Our editorial and stylistic standards
- Assessment of headline news worthiness

As Editor-in-Chief, your responsibility includes not only identifying issues but also exercising editorial judgment. Do not reject an article unless it contains substantial legal, factual, or ethical violations. Minor or technical issues should lead to correction suggestions, not rejection.

You must explain your reasoning clearly and explicitly. Each decision, observation, and conclusion must be logged step-by-step, with justification. This includes both the initial decision and any reconsideration. Do not omit or summarize critical steps. The rationale must be transparent, traceable, and match the final editorial outcome.

Proceed step by step through the following categories. For each step:
– Briefly state what was checked  
– Evaluate whether the article meets the criteria and why  
– List any issues and propose corrections if necessary

### Step 1: Legal Compliance
– No defamation, hate speech, or privacy violations  
– Correct attribution of quotes and sources  
– Follows Finnish Freedom of Expression Act and Criminal Code

### Step 2: Journalistic Accuracy & Balance
– Verifiable and sourced facts  
– Relevant perspectives fairly represented  
– No hidden conflicts of interest

### Step 3: Ethical Standards (JSN)
– Respect for privacy and human dignity  
– No misleading framing, headlines or omissions  
– Individuals treated fairly, with chance to respond if criticized

### Step 4: Style & Structure
– Clear and coherent structure: headline, subheadings, paragraphs  
– Professional, neutral tone  
– Proper use of quotes, context, statistics

### Step 5: Corrections & Accountability
– Identify significant legal, factual or ethical errors  
– Suggest clear corrections if needed  
– Correction policy is encouraged, but its absence is not grounds for rejection unless other serious accountability issues are present

### Step 6: Featured Article Assessment
This is CRITICAL for editorial decision-making.

Assess whether this article should be featured on the front page:

**Key Questions:**
- Does this affect many Finns or have broad public interest?
- Is this timely, breaking news or highly current?
- Would readers expect to see this as a top story?
- Is this more important than typical daily news?

**Guidelines:**
- Only 2-3 stories per day should be featured
- Featured articles should serve broad public interest
- Consider: politics, economy, major events, breaking news
- Avoid: routine announcements, very local news, niche topics

You must provide clear reasoning for your featured assessment.

### Step 7: Interview Decision
Decide whether this article requires additional interviews to provide balanced, comprehensive coverage:

**When interviews are typically needed:**
- Press releases: Independent expert perspective to verify claims
- Breaking news: Expert analysis or context from authorities
- Controversial topics: Multiple viewpoints for balance
- Technical subjects: Expert explanations for general audience
- Policy announcements: Affected parties' reactions

**When interviews are usually NOT needed:**
- Routine announcements with clear facts
- Event reports with sufficient eyewitness accounts
- Articles already containing expert quotes and analysis
- Time-sensitive breaking news where speed is critical
- If no contacts provided for interviews

**Interview method options:**
- **Phone**: Use for urgent breaking news, immediate expert reactions, emotional topics, or when real-time clarification is needed.
- **Email**: For detailed analysis, technical explanations, non-urgent topics, or when comprehensive written responses are preferred.

**Selection criteria:**
- Choose PHONE when: Urgency is high, topic requires immediate reaction, emotional nuance needed, or back-and-forth dialogue valuable
- Choose EMAIL when: Topic is complex/technical, detailed response needed, time is not critical, or contact prefers written communication

**Expertise areas to consider:**
- Subject matter experts (technology, economy, law, medicine, etc.)
- Affected stakeholders (citizens, organizations, industry representatives)
- Opposition voices or alternative perspectives
- Academic researchers or independent analysts

You must justify your interview decision based on journalistic value and public interest.

### Step 8: Final Checklist Review
Go through the following items and confirm if each one is satisfied. If any are not, explain why and how it can be fixed.
- [ ] All key facts are verified (minor unsourced details may be flagged but not block publication)  
- [ ] Legally compliant (no defamation, hate speech, or clear violations)  
- [ ] No major ethical violations  
- [ ] Balanced and fair representation of relevant perspectives  
- [ ] Correction policy present or not critical for this article type  
- [ ] Tone is professional and neutral
- [ ] Featured article assessment completed with proper justification
- [ ] Interview decision made with proper justification

### Important: Justify All Reasoning Transparently
You must log all observations and decisions.

For each step, explain what was checked, what was found, and how it contributed to the final decision. Your final explanation must clearly show why the article was accepted or rejected, AND why it received its specific featured article assessment. This review will be recorded for auditing purposes.

**Remember:** Not all controversy is avoidable or undesirable. Responsible journalism may challenge readers. Do not suppress legitimate reporting simply because it may offend or provoke—only reject content that clearly breaches law, ethics, or accuracy. However, featured articles should serve the broader public interest and have wide appeal.

### This is the Article to be Reviewed
**Title:** {article_title}

**Content:**
{generated_article_markdown}

**Additional Context:**
- Language: {language}
- Source Domain: {source_domain}
- Keywords: {keywords}
- Categories: {categories}
- Published: {published_at}
- Original Article Type: {original_article_type}
- Have contacts for interviews: {contact_info}
- Current local time (Europe/Helsinki): {current_local_time}
- Time of Review: Consider what other major news might be competing for headlines today
"""

# PROMPT WHEN PHONE INTERVIEWS ARE NOT ALLOWED (outside 08:00-18:00 Helsinki time)
EDITOR_IN_CHIEF_PROMPT_PHONE_NOT_ALLOWED = """
{persona}

Your task is to review the news article and verify that it complies with:
- Finnish journalistic law (Freedom of Expression Act, Criminal Code)
- JSN's Journalistin ohjeet (ethical code)
- Our editorial and stylistic standards
- Assessment of headline news worthiness

As Editor-in-Chief, your responsibility includes not only identifying issues but also exercising editorial judgment. Do not reject an article unless it contains substantial legal, factual, or ethical violations. Minor or technical issues should lead to correction suggestions, not rejection.

You must explain your reasoning clearly and explicitly. Each decision, observation, and conclusion must be logged step-by-step, with justification. This includes both the initial decision and any reconsideration. Do not omit or summarize critical steps. The rationale must be transparent, traceable, and match the final editorial outcome.

Proceed step by step through the following categories. For each step:
– Briefly state what was checked  
– Evaluate whether the article meets the criteria and why  
– List any issues and propose corrections if necessary

### Step 1: Legal Compliance
– No defamation, hate speech, or privacy violations  
– Correct attribution of quotes and sources  
– Follows Finnish Freedom of Expression Act and Criminal Code

### Step 2: Journalistic Accuracy & Balance
– Verifiable and sourced facts  
– Relevant perspectives fairly represented  
– No hidden conflicts of interest

### Step 3: Ethical Standards (JSN)
– Respect for privacy and human dignity  
– No misleading framing, headlines or omissions  
– Individuals treated fairly, with chance to respond if criticized

### Step 4: Style & Structure
– Clear and coherent structure: headline, subheadings, paragraphs  
– Professional, neutral tone  
– Proper use of quotes, context, statistics

### Step 5: Corrections & Accountability
– Identify significant legal, factual or ethical errors  
– Suggest clear corrections if needed  
– Correction policy is encouraged, but its absence is not grounds for rejection unless other serious accountability issues are present

### Step 6: Featured Article Assessment
This is CRITICAL for editorial decision-making.

Assess whether this article should be featured on the front page:

**Key Questions:**
- Does this affect many Finns or have broad public interest?
- Is this timely, breaking news or highly current?
- Would readers expect to see this as a top story?
- Is this more important than typical daily news?

**Guidelines:**
- Only 2-3 stories per day should be featured
- Featured articles should serve broad public interest
- Consider: politics, economy, major events, breaking news
- Avoid: routine announcements, very local news, niche topics

You must provide clear reasoning for your featured assessment.

### Step 7: Interview Decision
Decide whether this article requires additional interviews to provide balanced, comprehensive coverage:

**When interviews are typically needed:**
- Press releases: Independent expert perspective to verify claims
- Breaking news: Expert analysis or context from authorities
- Controversial topics: Multiple viewpoints for balance
- Technical subjects: Expert explanations for general audience
- Policy announcements: Affected parties' reactions

**When interviews are usually NOT needed:**
- Routine announcements with clear facts
- Event reports with sufficient eyewitness accounts
- Articles already containing expert quotes and analysis
- Time-sensitive breaking news where speed is critical
- If no contacts provided for interviews

**CURRENT TIME STATUS: Phone interviews NOT AVAILABLE (outside 08:00-18:00 Helsinki time)**

**Interview method options:**
- **Email**: REQUIRED - Must use email for all interviews outside business hours. Email allows for detailed responses, technical explanations, and gives contacts time to provide thoughtful answers.

**IMPORTANT:** You MUST select EMAIL as the interview method if interviews are needed.

**Expertise areas to consider:**
- Subject matter experts (technology, economy, law, medicine, etc.)
- Affected stakeholders (citizens, organizations, industry representatives)
- Opposition voices or alternative perspectives
- Academic researchers or independent analysts

You must justify your interview decision based on journalistic value and public interest.

### Step 8: Final Checklist Review
Go through the following items and confirm if each one is satisfied. If any are not, explain why and how it can be fixed.
- [ ] All key facts are verified (minor unsourced details may be flagged but not block publication)  
- [ ] Legally compliant (no defamation, hate speech, or clear violations)  
- [ ] No major ethical violations  
- [ ] Balanced and fair representation of relevant perspectives  
- [ ] Correction policy present or not critical for this article type  
- [ ] Tone is professional and neutral
- [ ] Featured article assessment completed with proper justification
- [ ] Interview decision made with proper justification

### Important: Justify All Reasoning Transparently
You must log all observations and decisions.

For each step, explain what was checked, what was found, and how it contributed to the final decision. Your final explanation must clearly show why the article was accepted or rejected, AND why it received its specific featured article assessment. This review will be recorded for auditing purposes.

**Remember:** Not all controversy is avoidable or undesirable. Responsible journalism may challenge readers. Do not suppress legitimate reporting simply because it may offend or provoke—only reject content that clearly breaches law, ethics, or accuracy. However, featured articles should serve the broader public interest and have wide appeal.

### This is the Article to be Reviewed
**Title:** {article_title}

**Content:**
{generated_article_markdown}

**Additional Context:**
- Language: {language}
- Source Domain: {source_domain}
- Keywords: {keywords}
- Categories: {categories}
- Published: {published_at}
- Original Article Type: {original_article_type}
- Have contacts for interviews: {contact_info}
- Current local time (Europe/Helsinki): {current_local_time}
- Time of Review: Consider what other major news might be competing for headlines today
"""


EDITOR_PERSONA = """
You are the Editor-in-Chief of a Finnish digital news platform. You have 15 years of experience in journalism, including 8 years as a senior editor at major Finnish newspapers. You are well-versed in:

- Finnish media law (Freedom of Expression Act, Criminal Code)
- JSN's ethical guidelines (Journalistin ohjeet)
- Modern digital journalism standards
- Editorial responsibility and accountability
- News value assessment and headline selection

Your editorial philosophy emphasizes:
- Accuracy and verification above speed
- Balanced reporting that serves the public interest
- Ethical treatment of all individuals and groups
- Legal compliance without sacrificing journalistic integrity
- Clear, accessible writing that respects readers' intelligence
- Strategic headline selection that maximizes public service and readership

You understand that headline news selection is crucial for:
- Attracting and retaining readers
- Serving the public interest
- Maintaining editorial credibility
- Competing effectively in the digital news landscape

You make decisions based on professional judgment, not personal opinion. You understand that journalism sometimes requires publishing uncomfortable truths, but you never compromise on accuracy, fairness, or legal compliance. You also understand that not every good story is headline material - headlines must serve the broader public interest and have wide appeal.

Your headline selection criteria prioritize:
1. Public interest and impact
2. Timeliness and relevance
3. Broad audience appeal
4. Editorial balance across different topics
5. Competitive positioning against other news sources
"""


class EditorInChiefAgent(BaseAgent):
    """An agent that reviews enriched articles for legal, ethical, and editorial compliance, including headline news assessment."""

    def __init__(self, llm, db_dsn: str):
        super().__init__(llm=llm, prompt=None, name="EditorInChiefAgent")
        self.structured_llm = self.llm.with_structured_output(ReviewedNewsItem)
        self.editorial_service = EditorialReviewService(db_dsn)
        self.db_dsn = db_dsn

        # Fetch the active prompt from database or use default
        self.active_prompt = self._get_active_persona_prompt()

    # Get active prompt from database, otherwise use default EDITOR_PERSONA
    def _get_active_persona_prompt(self) -> str:
        """Hae aktiivinen prompt tietokannasta synkronisesti (turvallinen FastAPIn event loopissa)."""
        print("KATOTAAS PROMPTIT TIETOKANNASTA! (sync)...")
        try:
            import psycopg

            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 
                            pc.id, pc.name, pc.fragment_ids,
                            pep.name as persona_name, pep.content as persona_content
                        FROM prompt_compositions pc
                        JOIN prompt_ethical_personas pep ON pc.ethical_persona_id = pep.id
                        WHERE pc.is_active = true
                        LIMIT 1
                        """
                    )
                    comp_result = cur.fetchone()
                    if not comp_result:
                        print(
                            "⚠️  No active prompt composition found, using default EDITOR_PERSONA"
                        )
                        return EDITOR_PERSONA

                    comp_id, comp_name, fragment_ids, persona_name, persona_content = (
                        comp_result
                    )
                    print(
                        f"✅ Using active prompt composition: '{comp_name}' (persona: {persona_name})"
                    )

                    ordered_fragments = []
                    if fragment_ids:
                        cur.execute(
                            """
                            SELECT id, content 
                            FROM prompt_fragments 
                            WHERE id = ANY(%s)
                            """,
                            (fragment_ids,),
                        )
                        fragment_rows = cur.fetchall()
                        fragment_dict = {row[0]: row[1] for row in fragment_rows}

                        # Säilytä fragmenttien järjestys fragment_ids:n mukaan
                        ordered_fragments = [
                            fragment_dict[fid]
                            for fid in fragment_ids
                            if fid in fragment_dict
                        ]

                    prompt_parts = [persona_content] + ordered_fragments
                    final_prompt = "\n\n".join(prompt_parts)
                    print(
                        f"📝 Loaded prompt with {len(ordered_fragments)} additional fragments"
                    )
                    return final_prompt

        except Exception as e:
            print(f"⚠️  Error loading active prompt from database: {e}")
            print("🔄 Falling back to default EDITOR_PERSONA")
            return EDITOR_PERSONA

    def _format_article_for_review(self, article: EnrichedArticle) -> str:
        """Format an enriched article for editorial review."""
        return f"""
        # {article.enriched_title}
        
        {article.enriched_content}
        
        ---
        **Summary:** {article.summary}
        **Sources:** {len(article.sources)} sources referenced
        """

    # Let's check if we have contacts for interviews...
    def _format_contact_info(self, article: EnrichedArticle) -> str:
        """Format contact information for the review prompt."""
        contacts = getattr(article, "contacts", []) or []

        if not contacts:
            return "No contacts available"

        contact_info_parts = []
        for i, contact in enumerate(contacts, 1):
            info = f"{i}. {contact.name}"
            if hasattr(contact, "title") and contact.title:
                info += f" ({contact.title})"
            if hasattr(contact, "organization") and contact.organization:
                info += f" - {contact.organization}"

            # Add contact methods
            methods = []
            if hasattr(contact, "email") and contact.email:
                methods.append("email")
            if hasattr(contact, "phone") and contact.phone:
                methods.append("phone")

            if methods:
                info += f" [Available: {', '.join(methods)}]"

            contact_info_parts.append(info)

        return "\n".join(contact_info_parts)

    def run(self, state: AgentState) -> AgentState:
        """Reviews an article and determines editorial decision."""
        print(
            "EditorInChiefAgent: Reviewing article for editorial compliance and headline assessment..."
        )

        if not hasattr(state, "current_article") or not state.current_article:
            print("EditorInChiefAgent: No current_article to review!")
            return state

        article: EnrichedArticle = state.current_article
        if not isinstance(article, EnrichedArticle):
            print(f"EditorInChiefAgent: Expected EnrichedArticle, got {type(article)}")
            return state

        try:
            # Get current time in Helsinki timezone
            helsinki_tz = ZoneInfo("Europe/Helsinki")
            current_time = datetime.now(helsinki_tz)
            current_local_time = current_time.strftime("%Y-%m-%d %H:%M:%S %Z")

            # Check if phone interviews are allowed at this time
            phone_allowed = is_phone_interview_time()

            # Select appropriate prompt based on time
            if phone_allowed:
                base_prompt = EDITOR_IN_CHIEF_PROMPT_PHONE_ALLOWED
                print(
                    f"📞 Phone interviews ARE AVAILABLE (current time: {current_local_time})"
                )
            else:
                base_prompt = EDITOR_IN_CHIEF_PROMPT_PHONE_NOT_ALLOWED
                print(
                    f"📧 Phone interviews NOT AVAILABLE - Email only (current time: {current_local_time})"
                )

            # Format the prompt with article details
            prompt_text = base_prompt.format(
                persona=self.active_prompt,
                article_title=article.enriched_title or "Untitled",
                generated_article_markdown=article.enriched_content or "",
                language=article.language or "unknown",
                source_domain=getattr(article, "source_domain", "unknown"),
                keywords=", ".join(article.keywords) if article.keywords else "none",
                categories=(
                    ", ".join(article.categories) if article.categories else "none"
                ),
                published_at=getattr(article, "published_at", "unknown"),
                original_article_type=getattr(
                    article, "original_article_type", "unknown"
                ),
                contact_info=self._format_contact_info(article),
                current_local_time=current_local_time,
            )

            # Get structured review from LLM
            review_result: ReviewedNewsItem = self.structured_llm.invoke(prompt_text)

            # Validate that phone interviews are not selected outside business hours
            if not phone_allowed and review_result.interview_decision:
                if review_result.interview_decision.interview_method == "phone":
                    print(
                        "⚠️  WARNING: LLM selected phone interview outside business hours. Forcing email."
                    )
                    review_result.interview_decision.interview_method = "email"
                    review_result.interview_decision.justification += (
                        " (Changed from phone to email due to time restrictions)"
                    )

            # Store in state for next agent
            state.review_result = review_result

            # Show editorial decision summary
            if review_result:
                print(f"\n{'='*60}")
                print(f"📋 EDITORIAL REVIEW COMPLETE")
                print(f"{'='*60}")
                print(f"   📄 Article: {article.enriched_title[:50]}...")
                print(f"   🎯 Status: {review_result.status}")
                print(
                    f"   📝 Decision: {getattr(review_result, 'editorial_decision', 'NOT_SET')}"
                )
                print(f"   ⚠️  Issues: {len(review_result.issues)} found")

                # Save review to database
                if article.news_article_id:
                    self.editorial_service.save_review(
                        article.news_article_id, review_result
                    )
                    print(
                        f"   💾 Review saved to database for article ID {article.news_article_id}"
                    )
                else:
                    print(
                        "   ⚠️  No article ID, review not saved (article not yet in database)"
                    )

                # Show headline news assessment
                if review_result.headline_news_assessment:
                    headline_assessment = review_result.headline_news_assessment
                    print(f"\n🏆 FEATURED-ARVIOINTI:")

                    featured_status = (
                        "✅ FEATURED"
                        if headline_assessment.featured
                        else "❌ EI FEATURED"
                    )
                    print(f"   🎯 Status: {featured_status}")
                    print(f"   📝 Perustelu: {headline_assessment.reasoning}")

                if review_result.interview_decision:
                    interview_decision = review_result.interview_decision
                    print(f"\n🎤 HAASTATTELUPÄÄTÖS:")

                    interview_status = (
                        "✅ TARVITAAN HAASTATTELU"
                        if interview_decision.interview_needed
                        else "❌ EI HAASTATTELUA"
                    )
                    print(f"   🎯 Status: {interview_status}")
                    print(f"   📝 Perustelu: {interview_decision.justification}")

                    if interview_decision.interview_needed:
                        if interview_decision.interview_method:
                            method_emoji = (
                                "📧"
                                if interview_decision.interview_method == "email"
                                else "📞"
                            )
                            print(
                                f"   {method_emoji} Menetelmä: {interview_decision.interview_method}"
                            )

                        if interview_decision.target_expertise_areas:
                            print(
                                f"   🎯 Asiantuntemus: {', '.join(interview_decision.target_expertise_areas)}"
                            )

                        if interview_decision.interview_focus:
                            print(f"   🔍 Fokus: {interview_decision.interview_focus}")

                        if interview_decision.article_type_influence:
                            print(
                                f"   📄 Artikkelityypin vaikutus: {interview_decision.article_type_influence}"
                            )

                # Show editorial reasoning process
                if review_result.editorial_reasoning:
                    reasoning = review_result.editorial_reasoning

                    print(f"\n🧠 PÄÄTTELYPROSESSI:")
                    print(f"   👤 Arvioija: {reasoning.reviewer}")
                    print(f"   🎯 Alkupäätös: {reasoning.initial_decision}")

                    print(f"\n📋 ARVIOIDUT KRITEERIT:")
                    for criterion in reasoning.checked_criteria:
                        status = (
                            "❌" if criterion in reasoning.failed_criteria else "✅"
                        )
                        print(f"   {status} {criterion}")

                    if reasoning.reasoning_steps:
                        print(f"\n🔍 VAIHEITTAINEN ARVIOINTI:")
                        for step in reasoning.reasoning_steps:
                            emoji = {"PASS": "✅", "FAIL": "❌", "INFO": "ℹ️"}.get(
                                step.result, "🔹"
                            )
                            print(f"\n   {step.step_id}. {emoji} {step.action}")
                            print(f"      💭 Havainto: {step.observation}")
                            print(f"      📊 Tulos: {step.result}")

                    print(f"\n📝 PÄÄTÖKSEN PERUSTELU:")
                    print(f"   {reasoning.explanation}")

                    # Show reconsideration if it happened
                    if reasoning.reconsideration:
                        recon = reasoning.reconsideration
                        print(f"\n🤔 UUDELLEENARVIOINTI:")
                        print(f"   🎯 Lopullinen päätös: {recon.final_decision}")
                        print(
                            f"   📋 Uudelleen arvioitut kriteerit: {', '.join(recon.failed_criteria)}"
                        )
                        if recon.reasoning_steps:
                            print(f"   🔍 Lisävaiheet:")
                            for step in recon.reasoning_steps:
                                emoji = {"PASS": "✅", "FAIL": "❌", "INFO": "ℹ️"}.get(
                                    step.result, "🔹"
                                )
                                print(
                                    f"      • {emoji} {step.action}: {step.observation}"
                                )
                        print(f"   💬 Selitys: {recon.explanation}")

                # Show issues found
                if review_result.issues:
                    print(f"\n⚠️  LÖYDETYT ONGELMAT ({len(review_result.issues)}):")
                    for i, issue in enumerate(review_result.issues, 1):
                        print(f"\n   {i}. {issue.type}")
                        print(f"      📍 Sijainti: {issue.location}")
                        print(f"      📝 Kuvaus: {issue.description}")
                        if issue.suggestion:
                            print(f"      💡 Ehdotus: {issue.suggestion}")

                print(f"{'='*60}\n")

        except Exception as e:
            import traceback

            print(f"❌ Error during editorial review: {e}")
            traceback.print_exc()

            # Create error review result
            error_review = ReviewedNewsItem(
                status="REJECT",
                editorial_decision="reject",  # VAIN virhetilanteessa reject
                issues=[
                    ReviewIssue(
                        type="Other",
                        location="Review Process",
                        description=f"Technical error: {str(e)}",
                        suggestion="Manual review required",
                    )
                ],
                editorial_reasoning=EditorialReasoning(
                    reviewer="EditorInChiefAgent",
                    initial_decision="REJECT",
                    checked_criteria=["Technical Review"],
                    failed_criteria=["Technical Review"],
                    reasoning_steps=[
                        ReasoningStep(
                            step_id=1,
                            action="Technical Review",
                            observation=f"Error: {str(e)}",
                            result="FAIL",
                        )
                    ],
                    explanation="Technical error during review",
                ),
                headline_news_assessment=HeadlineNewsAssessment(
                    featured=False, reasoning="Technical error prevented assessment"
                ),
                interview_decision=InterviewDecision(
                    interview_needed=False,
                    justification="Technical error prevented assessment",
                ),
            )
            state.review_result = error_review
            print(f"📋 Editorial decision: reject (technical error)")

        return state


if __name__ == "__main__":
    from dotenv import load_dotenv
    from langchain.chat_models import init_chat_model
    from schemas.enriched_article import EnrichedArticle, ArticleReference, LocationTag
    from schemas.agent_state import AgentState
    import os

    print("--- Running EditorInChiefAgent test WITHOUT Database (MOCK) ---")
    load_dotenv()

    # Run with this command:
    # python -m agents.editor_in_chief_agent

    # Initialize the LLM
    try:
        llm = init_chat_model("gpt-4o-mini", model_provider="openai")
        print("✅ LLM initialized successfully")
    except Exception as e:
        print(f"❌ Error initializing LLM: {e}")
        sys.exit(1)

    # Mock database service, we want skip database interactions in this test
    # This is just a placeholder to avoid real database connections
    class MockEditorialReviewService:
        """Mock service that doesn't actually connect to database"""

        def __init__(self, db_dsn):
            print(f"🎭 MockEditorialReviewService initialized (no real database)")
            self.db_dsn = db_dsn

        def save_review(self, news_article_id, review_result):
            print(
                f"🎭 MOCK SAVE: Would save review for news_article_id={news_article_id}"
            )
            print(f"     Status: {review_result.status}")
            print(
                f"     Editorial Decision: {getattr(review_result, 'editorial_decision', 'NOT_SET')}"
            )
            print(f"     Issues: {len(review_result.issues)} issues found")
            return True  # Always successful

    # Patch EditorInChiefAgent to use mock, just to skip database interactions

    def mock_init(self, llm, db_dsn: str):
        super(EditorInChiefAgent, self).__init__(
            llm=llm, prompt=None, name="EditorInChiefAgent"
        )
        self.structured_llm = self.llm.with_structured_output(ReviewedNewsItem)
        self.db_dsn = db_dsn

        # HAE OIKEA PROMPT TIETOKANNASTA (ei mock)
        self.active_prompt = self._get_active_prompt()

        # MOCK vain editorial service
        self.editorial_service = MockEditorialReviewService(db_dsn)

        EditorInChiefAgent.__init__ = mock_init

    # Create test enriched article
    # OBS! This article is trying to trigger interview!!!
    test_article = EnrichedArticle(
        article_id="test-article-1",
        canonical_news_id=123,
        news_article_id=1,  # Simulated database ID
        enriched_title="Testiuutinen: Suomen tekoälystategia etenee",
        enriched_content="""
# Suomen uusi tekoälystrategia: 100 miljoonan investointi tutkimukseen ja innovaatioihin

Suomen hallitus on julkaissut uuden tekoälystrategian, joka tähtää maan teknologisen kilpailukyvyn vahvistamiseen. Strategian ytimessä on 100 miljoonan euron panostus tekoälyn tutkimus- ja kehitystyöhön vuosina 2025–2027.

## Mihin panostetaan?

Investoinnin kohteena ovat:
- Yliopistojen tekoälytutkimuksen huippuyksiköt
- Startup-ekosysteemin kasvu ja kansainvälistyminen
- Julkisten palveluiden tekoälypohjainen uudistaminen

"Tämä strategia luo perustan Suomen digitaaliselle itsenäisyydelle ja kilpailukyvylle", sanoo teknologiaministeri.

## Miksi tämä on merkittävää?

Strategia vaikuttaa suoraan korkeakouluihin, yrityksiin ja kansalaisten arkeen. Se tarjoaa uusia mahdollisuuksia tutkimukselle, koulutukselle ja innovaatioille — sekä avaa ovia EU:n ja globaalin tekoälykilpailun ytimeen.

**Etsitkö asiantuntijaa kommentoimaan strategian vaikutuksia koulutukseen, tutkimukseen tai teknologiayrityksiin?**

Ota yhteyttä — järjestämme mielellämme haastattelun alan johtavien asiantuntijoiden kanssa.
        """,
        published_at="2024-01-15T10:00:00Z",
        source_domain="test.fi",
        keywords=["tekoäly", "strategia", "Suomi", "teknologia"],
        categories=["Teknologia", "Politiikka"],
        language="fi",
        sources=["https://example.com/source1", "https://example.com/source2"],
        references=[
            ArticleReference(
                title="Alkuperäinen uutinen", url="https://test.fi/original"
            ),
            ArticleReference(title="Lisätietoja", url="https://example.com/more"),
        ],
        locations=[
            LocationTag(
                continent="Europe", country="Finland", region="Uusimaa", city="Helsinki"
            ),
            LocationTag(continent="Europe", country="Finland", region=None, city=None),
        ],
        summary="Suomen hallitus julkisti uuden tekoälystrategian, joka sisältää 100 miljoonan euron panostuksen.",
        enrichment_status="success",
        original_article_type="press_release",
        contacts=[
            {
                "name": "Joni Honkanen",
                "title": "King of Tekoäly",
                "organization": "Tuni",
                "email": "joni.honkanen@testi.fi",
                "phone": "+358123456789",
                "contact_type": "spokesperson",
                "extraction_context": "Mentioned in press release",
                "is_primary_contact": True,
            }
        ],
    )

    initial_state = AgentState(
        current_article=test_article,
        enriched_articles=[test_article],
        reviewed_articles=[],
        review_result=None,
    )

    print(f"\nTest Setup:")
    print(f"- Article: {initial_state.current_article.enriched_title[:50]}...")
    print(f"- Enriched articles: {len(initial_state.enriched_articles)}")
    print(
        f"- Has news_article_id: {bool(initial_state.current_article.news_article_id)}"
    )

    # Test the agent with mock database
    try:
        print(f"\n--- Initializing EditorInChiefAgent (MOCK) ---")
        editor_agent = EditorInChiefAgent(llm, "mock://database/connection")
        print(f"✅ Agent initialized with mock database")

        print(f"\n--- Running editorial review ---")
        result_state = editor_agent.run(initial_state)
        print(f"✅ Agent run completed")

        # Display comprehensive results
        print(f"\n{'='*80}")
        print(f"🎉 TEST RESULTS (MOCK DATABASE)")
        print(f"{'='*80}")

        if hasattr(result_state, "review_result") and result_state.review_result:
            review = result_state.review_result

            print(f"\n📋 REVIEW OUTCOME:")
            print(f"   Status: {review.status}")

            # Debug editorial_decision
            ed = getattr(review, "editorial_decision", "NOT_FOUND")
            print(f"   Editorial Decision: {ed}")
            if ed == "NOT_FOUND":
                print(f"   ⚠️  Editorial Decision attribute missing!")
                print(f"   Available attributes: {list(review.__dict__.keys())}")

            # Featured assessment
            if review.headline_news_assessment:
                featured_status = (
                    "✅ FEATURED"
                    if review.headline_news_assessment.featured
                    else "❌ NOT FEATURED"
                )
                print(f"\n🏆 FEATURED ASSESSMENT:")
                print(f"   {featured_status}")
                print(f"   Reasoning: {review.headline_news_assessment.reasoning}")

            # Interview decision
            if review.interview_decision:
                interview_status = (
                    "✅ INTERVIEW NEEDED"
                    if review.interview_decision.interview_needed
                    else "❌ NO INTERVIEW"
                )
                print(f"\n🎤 INTERVIEW DECISION:")
                print(f"   {interview_status}")
                print(f"   Justification: {review.interview_decision.justification}")

                if review.interview_decision.interview_needed:
                    if review.interview_decision.interview_method:
                        print(
                            f"   Method: {review.interview_decision.interview_method}"
                        )
                    if review.interview_decision.target_expertise_areas:
                        print(
                            f"   Expertise areas: {', '.join(review.interview_decision.target_expertise_areas)}"
                        )

            # Issues found
            if review.issues:
                print(f"\n⚠️  ISSUES FOUND ({len(review.issues)}):")
                for i, issue in enumerate(review.issues, 1):
                    print(f"   {i}. {issue.type} - {issue.location}")
                    print(f"      Problem: {issue.description}")
                    print(f"      Suggestion: {issue.suggestion}")
            else:
                print(f"\n✅ NO ISSUES FOUND")

            # Editorial reasoning summary
            if review.editorial_reasoning:
                reasoning = review.editorial_reasoning
                print(f"\n🧠 REASONING PROCESS:")
                print(f"   Reviewer: {reasoning.reviewer}")
                print(f"   Initial Decision: {reasoning.initial_decision}")
                print(f"   Checked Criteria: {len(reasoning.checked_criteria)} items")
                print(f"   Failed Criteria: {len(reasoning.failed_criteria)} items")
                if reasoning.reasoning_steps:
                    print(f"   Reasoning Steps: {len(reasoning.reasoning_steps)} steps")

            # Success metrics
            print(f"\n📊 TEST METRICS:")
            print(f"   ✅ LLM structured output: SUCCESS")
            print(f"   ✅ Database save: MOCKED")
            print(
                f"   ✅ Editorial decision made: {'SUCCESS' if ed != 'NOT_FOUND' else 'FAIL'}"
            )
            print(
                f"   ✅ Featured assessment: {'SUCCESS' if review.headline_news_assessment else 'FAIL'}"
            )
            print(
                f"   ✅ Interview decision: {'SUCCESS' if review.interview_decision else 'FAIL'}"
            )

        else:
            print(f"❌ NO REVIEW RESULT FOUND")
            print(f"   Check that the agent properly processes current_article")

        # Final validation
        print(f"\n🔍 FINAL VALIDATION:")
        print(f"   Original article ID: {initial_state.current_article.article_id}")
        print(f"   News article ID: {initial_state.current_article.news_article_id}")
        print(f"   Review completed: {bool(result_state.review_result)}")

        if result_state.review_result:
            print(
                f"   Decision flow: {result_state.review_result.status} → {getattr(result_state.review_result, 'editorial_decision', 'NOT_SET')}"
            )

        print(f"\n✅ Test completed successfully WITHOUT database!")
        print(f"🎭 All database operations were mocked")

    except Exception as e:
        print(f"\n❌ ERROR IN TEST: {e}")
        import traceback

        print(f"\nFull traceback:")
        traceback.print_exc()

        print(f"\n🔧 TROUBLESHOOTING:")
        print(f"   1. Check OPENAI_API_KEY in .env")
        print(f"   2. Verify all required dependencies are installed")
        print(f"   3. Check that structured output schema is correct")


# Agent flow (before and after):
# ... -> article_storer_agent -> EDITOR_IN_CHIEF_AGENT (WE ARE HERE) -> *after this we have many options*
#  -> article_publisher_agent || -> interview_agent || -> article_reviser_agent || -> reject_agent
