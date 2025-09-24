# File: agents/editor_in_chief_agent.py

import sys
import os

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

# TODO:: SKEEMASSA KÄYTETÄÄN KAHDESSA KOHTAAN "reconsideration", mikä voi sekoittaa kielimallin! EditorialReasoning.reconsideration ja ReviewedNewsItem.reconsideration
# TODO:: KORJAA!! Tämä vaikuttaa myös tietokantaan jne...

EDITOR_IN_CHIEF_PROMPT = """
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
This is CRITICAL for editorial decision-making. Assess whether this article should be featured on the front page:

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

**Interview method considerations:**
- **Phone**: For urgent breaking news, immediate expert reactions
- **Email**: For detailed analysis, technical explanations, non-urgent topics

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
You must log all observations and decisions. For each step, explain what was checked, what was found, and how it contributed to the final decision. Your final explanation must clearly show why the article was accepted or rejected, AND why it received its specific featured article assessment. This review will be recorded for auditing purposes.

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


# TODO:: Meillä on tieto alkuperäisestä artikkelityypistä, sekä onko meillä yhteystietoja...
# TODO:: Nämä seikat voisivat vaikuttaa siihen, tarvitaanko haastatteluja vai ei.
# TODO:: ESIM jos tyyppinä "press release" ja yhteystiedot löytyy, niin voidaan haastatella...
# TODO:: Jos uutinen saa arvoksi "high", niin voidaan harkita puhelinhaastatteluja...
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
                        print("⚠️  No active prompt composition found, using default EDITOR_PERSONA")
                        return EDITOR_PERSONA

                    comp_id, comp_name, fragment_ids, persona_name, persona_content = comp_result
                    print(f"✅ Using active prompt composition: '{comp_name}' (persona: {persona_name})")

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
                            fragment_dict[fid] for fid in fragment_ids if fid in fragment_dict
                        ]

                    prompt_parts = [persona_content] + ordered_fragments
                    final_prompt = "\n\n".join(prompt_parts)
                    print(f"📝 Loaded prompt with {len(ordered_fragments)} additional fragments")
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
        print("CONTACT INFO")
        print(article.contacts)
        if not article.contacts or len(article.contacts) == 0:
            return "No contacts available for interviews"

        contact_descriptions = []
        for contact in article.contacts:
            # Build contact description
            contact_desc = f"{contact.name}"
            if hasattr(contact, "title") and contact.title:
                contact_desc += f" ({contact.title})"
            if hasattr(contact, "organization") and contact.organization:
                contact_desc += f" from {contact.organization}"

            # Add available contact methods
            methods = []
            if hasattr(contact, "email") and contact.email:
                methods.append("email")
            if hasattr(contact, "phone") and contact.phone:
                methods.append("phone")

            if methods:
                contact_desc += f" - Available via: {', '.join(methods)}"
            else:
                contact_desc += " - No contact methods provided"

            contact_descriptions.append(contact_desc)

        return f"{len(article.contacts)} contact(s) available: " + "; ".join(
            contact_descriptions
        )

    def review_article(self, article: EnrichedArticle) -> ReviewedNewsItem:
        """Review a single enriched article and save to database."""
        print(f"🔍 Reviewing: {article.enriched_title[:60]}...")

        # Check if article has been stored to database
        if not article.news_article_id:
            print(f"❌ Article {article.article_id} has no news_article_id!")
            print("   This article was not properly stored to database.")
            print("   Cannot save editorial review without news_article_id.")

            # Create error review but don't try to save it
            return ReviewedNewsItem(
                status="ISSUES_FOUND",
                issues=[
                    ReviewIssue(
                        type="Other",
                        location="Review Process",
                        description="Article not stored in database - missing news_article_id",
                        suggestion="Ensure ArticleStorerAgent runs before EditorInChiefAgent",
                    )
                ],
                editorial_reasoning=EditorialReasoning(
                    reviewer="EditorInChiefAgent",
                    initial_decision="REJECT",
                    checked_criteria=["Database Storage"],
                    failed_criteria=["Database Storage"],
                    reasoning_steps=[
                        ReasoningStep(
                            step_id=1,
                            action="Check Database Storage",
                            observation="Article has no news_article_id",
                            result="FAIL",
                        )
                    ],
                    explanation="Cannot review article that is not stored in database",
                ),
                headline_news_assessment=HeadlineNewsAssessment(
                    featured=False,
                    reasoning="Technical error prevented proper featured assessment",
                ),
                interview_decision=InterviewDecision(
                    interview_needed=False,
                    justification="Technical error prevented proper interview assessment",
                ),
            )

        print(f"📋 Using news_article.id: {article.news_article_id}")

        # Format the article content for review
        formatted_content = self._format_article_for_review(article)

        # Format contact information
        contact_info = self._format_contact_info(article)

        print("TÄTÄ KÄYTETÄÄN!")
        print(self.active_prompt)

        # Prepare the prompt
        prompt_content = EDITOR_IN_CHIEF_PROMPT.format(
            persona=self.active_prompt,  # get persona from db, or use default
            article_title=article.enriched_title,
            generated_article_markdown=formatted_content,
            language=article.language,
            source_domain=article.source_domain,
            keywords=", ".join(article.keywords),
            categories=", ".join(article.categories),
            published_at=article.published_at,
            original_article_type=article.original_article_type or "unknown",
            contact_info=contact_info,
        )

        # if you want check how prompts look like, you can uncomment this line
        print(prompt_content)

        try:
            # Get structured review from LLM
            review_result: ReviewedNewsItem = self.structured_llm.invoke(prompt_content)

            # Save to database using news_article_id
            success = self.editorial_service.save_review(
                article.news_article_id, review_result
            )

            if success:
                print(
                    f"💾 Saved editorial review to database for news_article.id {article.news_article_id}"
                )
            else:
                print(
                    f"⚠️  Failed to save editorial review for news_article.id {article.news_article_id}"
                )

            # Show headline news assessment
            if review_result.headline_news_assessment:
                headline_assessment = review_result.headline_news_assessment
                print(f"\n🏆 FEATURED-ARVIOINTI:")

                featured_status = (
                    "✅ FEATURED" if headline_assessment.featured else "❌ EI FEATURED"
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
                    status = "❌" if criterion in reasoning.failed_criteria else "✅"
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
                            print(f"      • {emoji} {step.action}: {step.observation}")
                    print(f"   💬 Selitys: {recon.explanation}")

            # Show issues found
            if review_result.issues:
                print(f"\n⚠️  LÖYDETYT ONGELMAT ({len(review_result.issues)}):")
                for i, issue in enumerate(review_result.issues, 1):
                    print(f"\n   {i}. {issue.type.upper()} - {issue.location}")
                    print(f"      🔍 Ongelma: {issue.description}")
                    print(f"      💡 Ehdotus: {issue.suggestion}")

            # Show approval comment if given
            if review_result.approval_comment:
                print(f"\n✅ HYVÄKSYNTÄKOMMENTTI:")
                print(f"   {review_result.approval_comment}")

            # Show editorial warning if issued
            if review_result.editorial_warning:
                warning = review_result.editorial_warning
                print(f"\n⚠️  TOIMITUKSELLINEN VAROITUS:")
                print(f"   📂 Kategoria: {warning.category}")
                print(f"   📝 Lukijoille: {warning.details}")
                if warning.topics:
                    print(f"   🏷️  Aiheet: {', '.join(warning.topics)}")

            # Show final reconsideration if separate from reasoning
            if (
                review_result.reconsideration
                and not review_result.editorial_reasoning.reconsideration
            ):
                recon = review_result.reconsideration
                print(f"\n🎯 LOPULLINEN UUDELLEENARVIOINTI:")
                print(f"   📊 Päätös: {recon.final_decision}")
                print(f"   💬 Perustelu: {recon.explanation}")

            print(f"\n{'='*80}")

            return review_result

        except Exception as e:
            print(f"❌ Virhe arvioinnissa: {e}")
            # Return a default "issues found" review in case of error
            error_review = ReviewedNewsItem(
                status="ISSUES_FOUND",
                issues=[
                    ReviewIssue(
                        type="Other",
                        location="Review Process",
                        description=f"Technical error during review: {str(e)}",
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
                            observation=f"Error occurred: {str(e)}",
                            result="FAIL",
                        )
                    ],
                    explanation=f"Technical error prevented proper review: {str(e)}",
                ),
                headline_news_assessment=HeadlineNewsAssessment(
                    featured=False,
                    reasoning="Technical error prevented proper featured assessment",
                ),
            )

            # Try to save error review if we have news_article_id
            if article.news_article_id:
                try:
                    self.editorial_service.save_review(
                        article.news_article_id, error_review
                    )
                    print(
                        f"💾 Saved error review to database for news_article.id {article.news_article_id}"
                    )
                except Exception as save_error:
                    print(f"⚠️  Could not save error review to database: {save_error}")

            return error_review

    def run(self, state: AgentState) -> AgentState:
        """Run editor-in-chief review for single article in subgraph."""

        if not hasattr(state, "current_article") or not state.current_article:
            print("❌ Ei current_article -kenttää!")
            return state

        print(
            f"📰 ARVIOINTI: {getattr(state.current_article, 'enriched_title', 'Unknown')[:50]}..."
        )

        try:
            # TEE REVIEW
            review_result = self.review_article(state.current_article)
            print(f"📋 Arviointi valmis: {review_result.status}")

            # ASETA EDITORIAL DECISION
            if review_result.status == "OK":
                if review_result.interview_decision.interview_needed:
                    review_result.editorial_decision = "interview"
                    print(f"🎤 Päätös: HAASTATTELU tarvitaan")
                else:
                    review_result.editorial_decision = "publish"
                    print(f"✅ Päätös: JULKAISU")
            elif review_result.status == "ISSUES_FOUND":
                # Useimmat ongelmat voidaan korjata → revise
                review_result.editorial_decision = "revise"
                print(
                    f"🔧 Päätös: KORJAUS (löytyi {len(review_result.issues)} ongelmaa)"
                )
            else:  # RECONSIDERATION
                review_result.editorial_decision = "revise"
                print(f"🤔 Päätös: HARKINTA → KORJAUS")

            # TALLENNA TULOS
            state.review_result = review_result

            print(f"📋 Editorial decision: {review_result.editorial_decision}")

        except Exception as e:
            print(f"❌ Virhe arvioinnissa: {e}")

            # Luo error review - VAIN TÄSSÄ käytetään "reject"
            from schemas.editor_in_chief_schema import (
                ReviewedNewsItem,
                ReviewIssue,
                EditorialReasoning,
                HeadlineNewsAssessment,
                InterviewDecision,
                ReasoningStep,
            )

            error_review = ReviewedNewsItem(
                status="ISSUES_FOUND",
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
