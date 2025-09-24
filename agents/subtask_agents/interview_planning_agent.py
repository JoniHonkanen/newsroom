import os
from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle
from schemas.editor_in_chief_schema import InterviewDecision
from schemas.parsed_article import NewsContact
from schemas.interview_schema import (
    InterviewPlan,
    InterviewQuestion,
    EmailInterviewPlan,
    PhoneInterviewPlan,
)
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import json
from dotenv import load_dotenv

load_dotenv()

# Updated Interview Planning Prompt - POISTETTU priority-viittaukset
INTERVIEW_PLANNING_PROMPT = """
You are an experienced journalist responsible for planning interviews to strengthen articles.

You have been given:
1. An article that needs additional perspectives
2. Editorial feedback about what kind of interviews are needed
3. Selected contact for the interview

Your task is to first identify the **main point (beef)** of the article, and then create a comprehensive interview plan that addresses the editorial concerns and strengthens the article's journalistic balance.

## ARTICLE TO STRENGTHEN:

**Title:** {article_title}

**Content:**
{article_content}

## EDITORIAL REQUIREMENTS:

**Interview Method:** {interview_method}
**Target Expertise Areas:** {target_expertise}
**Interview Focus (this is important!):** {interview_focus}
**Justification:** {justification}

## SELECTED CONTACT:

{selected_contact}

## PLANNING GUIDELINES:

### STEP 1: Identify the main point
- Read the article carefully.
- Write 1-2 sentences in your own words that capture the article's **main point**.
- This is the underlying story essence, beyond surface details.
- Interview questions should be built around this main point.

### STEP 2: Method selection
- **Phone**: For urgent news, emotional topics, or complex explanations
- **Email**: For expert opinions, fact-checking, or when detailed responses are needed

### STEP 3: Interview style guidelines
1. Adjust the **depth and tone** of your questions to match the article's character.
   - Analytical / policy → deeper, structured
   - Light / participatory → accessible, engaging
   - Human-interest / cultural → meaning, stories, emotions
2. Balance your questions:
   - At least one open, inviting question
   - At least one specific, detail-oriented question
   - Make sure the set feels natural for the article's tone

### STEP 4: Question strategy
- Build all questions so they clearly connect to both:
  1. The article's **main point**
  2. The **Interview Focus** (as specified by the Editor-in-Chief)
- Use open-ended questions that fit the tone above.
- Address editorial requirements directly.
- Keep balance between detail and accessibility.
- **Important for phone interviews:** Keep questions short, clear, and easy to understand. Avoid overly complex or multi-part questions that might confuse the interviewee or slow the conversation.


## Summary:

Create a detailed interview plan (2-4 questions) that:
- Matches the tone to the article type
- Fulfills the editorial requirements
- Is appropriate for the interview method
"""


class InterviewPlanningAgent(BaseAgent):
    """Agent that creates detailed interview plans for articles requiring additional sources."""

    def __init__(self, llm, db_dsn: str):
        super().__init__(
            llm=llm, prompt=INTERVIEW_PLANNING_PROMPT, name="InterviewPlanningAgent"
        )
        self.db_dsn = db_dsn
        self.question_llm = llm

    def run(self, state: AgentState) -> AgentState:
        """Creates interview plan based on editorial feedback."""
        print("📞 INTERVIEW PLANNING AGENT: Creating interview plan...")

        if not hasattr(state, "current_article") or not state.current_article:
            print(
                "❌ InterviewPlanningAgent: No current_article to plan interviews for!"
            )
            return state

        article: EnrichedArticle = state.current_article
        if not isinstance(article, EnrichedArticle):
            print(
                f"❌ InterviewPlanningAgent: Expected EnrichedArticle, got {type(article)}"
            )
            return state

        if not hasattr(state, "review_result") or not state.review_result:
            print(
                "❌ InterviewPlanningAgent: No review_result with interview decision!"
            )
            return state

        interview_decision = state.review_result.interview_decision
        if not interview_decision or not interview_decision.interview_needed:
            print(
                "❌ InterviewPlanningAgent: No interview needed according to editorial decision!"
            )
            return state

        print(f"📰 Planning interviews for: {article.enriched_title[:50]}...")
        print(f"🎯 Method: {interview_decision.interview_method}")
        print(f"🔍 Focus: {interview_decision.interview_focus}")
        print(
            f"👥 Target areas: {', '.join(interview_decision.target_expertise_areas)}"
        )

        # Get available contacts and select the best one early
        available_contacts = getattr(article, "contacts", []) or []
        print(f"📋 Available contacts: {len(available_contacts)}")

        # Select contact based on interview method
        if interview_decision.interview_method == "email":
            selected_contact = self._select_and_format_email_contact(available_contacts)
        else:
            selected_contact = self._select_and_format_phone_contact(available_contacts)

        print(
            f"👤 Selected contact: {selected_contact['name'] if selected_contact else 'None'}"
        )

        # If phone is required but no phone-capable contact found, fall back to email if possible
        if interview_decision.interview_method == "phone" and not selected_contact:
            print(
                "⚠️ No phone-capable contact found. Falling back to email interview if email is available."
            )
            email_fallback = self._select_and_format_email_contact(available_contacts)
            if email_fallback:
                try:
                    interview_plan = self._create_email_plan(
                        article, interview_decision, available_contacts, email_fallback
                    )
                    # Override method to email since we fell back
                    interview_plan.interview_method = "email"
                    state.interview_plan = interview_plan
                    return state
                except Exception as e:
                    print(f"❌ Error creating fallback email plan: {e}")
            else:
                print("❌ No usable contact for email fallback either (missing email).")

        try:
            # Create method-specific interview plan
            # DO WE WANT EMAIL OR PHONE INTERVIEW !!!
            # IDEA IS, PHONE IF ITS URGENT THING!
            if interview_decision.interview_method == "email":
                interview_plan = self._create_email_plan(
                    article, interview_decision, available_contacts, selected_contact
                )
            else:  # phone
                interview_plan = self._create_phone_plan(
                    article, interview_decision, available_contacts, selected_contact
                )

            # Add to state
            state.interview_plan = interview_plan

            return state

        except Exception as e:
            print(f"❌ Error creating interview plan: {e}")
            import traceback

            traceback.print_exc()

            state.interview_plan = None
            print("⚠️ Failed to create interview plan")

            return state

    def _create_email_plan(
        self,
        article: EnrichedArticle,
        interview_decision: InterviewDecision,
        available_contacts: List[NewsContact],
        selected_contact: dict,
    ) -> InterviewPlan:
        """Create email-specific interview plan with formatted email body."""

        # Use the pre-selected contact
        email_contact = selected_contact.get("email") if selected_contact else None
        if not email_contact:
            email_contact = "ei-sahkopostia@example.com"

        # Get article language
        article_language = getattr(article, "language", "fi")

        # Generate questions (2-5 questions) in article language using LLM
        questions = self._generate_questions_from_areas(
            interview_decision.target_expertise_areas[:3],
            interview_decision.interview_focus,
            article.enriched_title,
            language=article_language,
            interview_type="email",
        )

        # Create subject in article language
        if article_language == "fi":
            subject = f"Kysymyksiä artikkelista: {article.enriched_title[:50]}..."
        else:
            subject = f"Questions about article: {article.enriched_title[:50]}..."

        # Format complete email body
        formatted_email_body = self._format_email_body(
            article, interview_decision, questions, article_language
        )

        email_plan = EmailInterviewPlan(
            news_article_id=article.news_article_id,
            recipient=email_contact,
            subject=subject,
            questions=questions,
            background_context=interview_decision.interview_focus,
            target_expertise_areas=interview_decision.target_expertise_areas,
            interview_focus=interview_decision.interview_focus,
            formatted_email_body=formatted_email_body,
        )

        return InterviewPlan(
            canonical_news_id=article.canonical_news_id,
            article_id=article.news_article_id,
            interview_method="email",
            email_plan=email_plan,
            available_contacts=available_contacts,
        )

    def _format_email_body(
        self,
        article: EnrichedArticle,
        interview_decision: InterviewDecision,
        questions: List[InterviewQuestion],
        language: str = "fi",
    ) -> str:
        """Format complete email body with intro, questions, outro, and signature."""

        # Intro/greeting
        if language == "fi":
            intro = f"""Hei, olen tekoälyjournalisti Tampereen yliopistosta.

Teen journalistista juttua aiheestanne "{article.enriched_title}".

Haluaisin kysyä muutaman tarkentavan kysymyksen aiheeseen liittyen:"""
        else:
            intro = f"""Hello, I am an AI journalist from the University of Tampere.

I am working on a journalistic article about  "{article.enriched_title}".

I would like to ask a few clarifying questions related to this topic:"""

        # Format questions by topic
        questions_section = "\n"
        current_topic = None

        for question in questions:
            if question.topic != current_topic:
                questions_section += f"\n**{question.topic.title()}:**\n"
                current_topic = question.topic

            # Käytä position-numeroa
            questions_section += f"{question.position}. {question.question}\n"

        # Outro
        if language == "fi":
            outro = """
Kiitos ajastanne! Vastaukset käsitellään osana tekoälyavusteista tutkimusta, jossa tekoäly toimii journalistina.
https://www.tuni.fi/fi/tutkimus/tekoalyn-johtama-uutistoimitus"""
        else:
            outro = """
Thank you for your time! The responses will be processed as part of AI-assisted research where AI acts as a journalist.
https://www.tuni.fi/fi/tutkimus/tekoalyn-johtama-uutistoimitus"""

        # Signature
        if language == "fi":
            signature = """
Ystävällisin terveisin,

Teppo Tekoälyjournalisti
– tutkimushanke Tampereen yliopisto"""
        else:
            signature = """
Best regards,

Teppo AI Journalist
– research project, University of Tampere"""

        # Combine all parts
        email_body = intro + questions_section + outro + signature

        return email_body

    def _create_phone_plan(
        self,
        article: EnrichedArticle,
        interview_decision: InterviewDecision,
        available_contacts: List[NewsContact],
        selected_contact: dict,
    ) -> InterviewPlan:
        """Create phone-specific interview plan with JSON structure for Realtime API."""

        # Use the pre-selected contact
        phone_contact = selected_contact.get("to_number") if selected_contact else None
        if (
            not phone_contact
            or not isinstance(phone_contact, str)
            or not phone_contact.strip()
        ):
            raise ValueError("No phone number available for selected contact")

        # Get article language
        article_language = getattr(article, "language", "fi")

        # Generate questions (2-5 questions) in article language using LLM
        questions = self._generate_questions_from_areas(
            interview_decision.target_expertise_areas[:3],
            interview_decision.interview_focus,
            article.enriched_title,
            language=article_language,
            interview_type="call",
        )

        # Create JSON-structured phone script for Realtime API
        phone_script_json = self._create_phone_script_json(
            questions,
            article.enriched_title,
            article_language,
        )

        phone_plan = PhoneInterviewPlan(
            to_number=phone_contact,
            phone_script_json=phone_script_json,
        )

        print("AAAAAAAAAAAAAAAAAAAA")
        print(phone_contact)
        print(phone_script_json)
        print(article.canonical_news_id)
        print(article.news_article_id)

        interview_plan_for_phone = InterviewPlan(
            canonical_news_id=article.canonical_news_id,
            article_id=article.news_article_id,
            interview_method="phone",
            phone_plan=phone_plan,
            available_contacts=available_contacts,
        )

        print(interview_plan_for_phone)

        return interview_plan_for_phone

    def _create_phone_script_json(
        self,
        questions: List[InterviewQuestion],
        title: str,
        language: str = "fi",
    ) -> dict:
        """Create hybrid JSON-structured phone interview script for OpenAI Realtime API."""

        if language == "fi":
            rules = [
                "Kysy VAIN 2 pääkysymystä. Älä keksi lisäkysymyksiä.",
                "Älä vastaa omiin kysymyksiisi. Kun haastateltava on valmis, kysy seuraava kysymys.",
                "Puhu vain suomea koko haastattelun ajan.",
                "Kysy vain yksi kysymys kerrallaan ja odota vastaus.",
                "2 pääkysymyksen jälkeen kysy: 'Onko jotain mitä haluatte vielä kertoa aiheesta?'",
                "Lopetuksen jälkeen kiitä ja pyydä sulkemaan puhelu.",
            ]
            instructions = (
                f"Olet Tampereen yliopiston tekoäly, joka tekee LYHYEN haastattelun.\n"
                "Kun esittelet itsesi, kerro että teet haastattelua artikkelia varten, mutta älä lue koko otsikkoa ääneen.\n"
                "Sen sijaan kuvaile aihe lyhyesti ja luonnollisesti omilla sanoillasi.\n"
                "HAASTATTELUN RAKENNE:\n"
                "1. Aloita: 'Hei, olen Tampereen yliopiston tekoälyjournalisti. Teen lyhyttä haastattelua [kuvaile aihe lyhyesti]'\n"
                "2. Kysy lupa jatkaa\n"
                "3. Esitä 2 pääkysymystä yksi kerrallaan, odota vastaus jokaiseen\n"
                "4. Lopuksi kysy: 'Onko jotain mitä haluatte vielä kertoa aiheesta?'\n"
                "5. Kuuntele vastaus ja kiitä haastattelusta\n"
                "6. Lopeta haastattelu kohteliaasti\n"
                "Pysy suomen kielessä koko ajan."
            )
            voice = "nova"

        else:  # English
            rules = [
                "Ask ONLY 2 main questions. Do not make up additional questions.",
                "Do not answer your own questions.",
                "Speak only in English throughout the interview.",
                "Ask one question at a time and wait for response.",
                "After 2 main questions, ask: 'Is there anything else you'd like to add about this topic?'",
                "After that, thank and end the interview.",
            ]
            instructions = (
                f"You are conducting a SHORT phone interview for a news article.\n"
                "When introducing yourself, mention you're doing an interview for an article, but don't read the full headline aloud.\n"
                "Instead, describe the topic briefly and naturally in your own words.\n"
                "INTERVIEW STRUCTURE:\n"
                "1. Start: 'Hello, I'm an AI journalist from University of Tampere. I'm conducting a short interview about [describe topic briefly]'\n"
                "2. Ask for permission to continue\n"
                "3. Ask 2 main questions one by one, wait for each response\n"
                "4. Finally ask: 'Is there anything else you'd like to add about this topic?'\n"
                "5. Listen to the response and thank the interviewee\n"
                "6. End the interview politely\n"
                "Stay in English throughout."
            )
            voice = "alloy"

        # Valitse oikea lopetuskysymys kielen mukaan
        closing_question_text = (
            "Onko jotain mitä haluatte vielä kertoa aiheesta?"
            if language == "fi"
            else "Is there anything else you'd like to add about this topic?"
        )

        config = {
            "role": "system",
            "rules": rules,
            "instructions": instructions,
            "voice": voice,
            "temperature": 0.7,
            "language": language,
            "interview_structure": "2 main questions + 1 closing question",
            "article_title": title,
            "questions_data": [
                {"position": q.position, "topic": q.topic, "text": q.question}
                for q in questions
            ],
            "closing_question": closing_question_text,
        }

        return config

    def _select_and_format_email_contact(self, contacts: List[NewsContact]) -> dict:
        """Select best email contact and format for LLM prompt."""
        selected = None

        # First, try to find primary contact with email
        for contact in contacts:
            if contact.email and contact.is_primary_contact:
                selected = contact
                break

        # Fallback to first available email
        if not selected:
            for contact in contacts:
                if contact.email:
                    selected = contact
                    break

        if selected:
            return {
                "name": selected.name,
                "title": selected.title,
                "organization": selected.organization,
                "email": selected.email,
                "contact_type": selected.contact_type,
                "context": selected.extraction_context,
            }
        return None

    def _select_and_format_phone_contact(self, contacts: List[NewsContact]) -> dict:
        """Select best phone contact and format for LLM prompt."""
        selected = None

        # First, try to find primary contact with phone
        for contact in contacts:
            if contact.phone and contact.is_primary_contact:
                selected = contact
                break

        # Fallback to first available phone
        if not selected:
            for contact in contacts:
                if contact.phone:
                    selected = contact
                    break

        if selected:
            return {
                "name": selected.name,
                "title": selected.title,
                "organization": selected.organization,
                # "to_number": selected.phone,
                "to_number": os.getenv("CONTACT_PERSON_PHONE"),
                "contact_type": selected.contact_type,
                "context": selected.extraction_context,
            }
        return None

    def _generate_questions_from_areas(
        self,
        expertise_areas: List[str],
        focus: str,
        title: str,
        language: str = "fi",
        interview_type: str = "email",
    ) -> List[InterviewQuestion]:
        """Generate 2-4 interview questions based on expertise areas and focus using LLM."""

        language_name = "Finnish" if language == "fi" else "English"
        if interview_type == "call":
            num_questions = 2  # Kiinteästi 2 kysymystä puhelinhaastattelulle
        else:
            num_questions = min(len(expertise_areas) + 1, 4)  # Sähköpostille ennallaan

        # Prompt templates
        if interview_type == "call":
            prompt_template = f"""
    Olet kokenut journalisti, ja tehtäväsi on tehdä lyhyt puhelinhaastattelu artikkelia varten.

    ## KONTEKSTI:
    **Artikkelin otsikko:** {title}
    **Haastattelun fokus:** {focus}
    **Asiantuntemusalueet:** {', '.join(expertise_areas)}
    **Kieli:** {language_name}
    **Haastattelutyyppi:** Puhelinhaastattelu

    ## TEHTÄVÄ:
    Luo TARKALLEEN {num_questions} kysymystä, jotka:
    1. Ovat lyhyitä ja helposti ymmärrettäviä puhuttaessa (max 15 sanaa).
    2. Käsittelevät vain yhtä aihetta per kysymys.
    3. Alkavat toimintasanoilla kuten "Kerro", "Kuvaile", "Mitä".
    4. Pysyvät haastattelun fokuksessa.
    5. Ovat täysin suomenkielisiä.

    ## OHJEET:
    - Luo yksi kysymys kutakin asiantuntemusaluetta kohden (max 3)
    - Lisää yksi yleinen kysymys
    - Kysymysten tulee olla loogisessa järjestyksessä (tärkein ensin)
    - Vältä monimutkaisia sivulauseita
    """
        else:  # email
            prompt_template = f"""
    Olet kokenut journalisti, ja tehtäväsi on tehdä sähköpostitse lähetettävä haastattelu artikkelia varten.

    ## KONTEKSTI:
    **Artikkelin otsikko:** {title}
    **Haastattelun fokus:** {focus}
    **Asiantuntemusalueet:** {', '.join(expertise_areas)}
    **Kieli:** {language_name}
    **Haastattelutyyppi:** Sähköposti

    ## TEHTÄVÄ:
    Luo {num_questions} kysymystä, jotka:
    1. Ovat hieman muodollisempia ja syvempiä kuin puhelussa.
    2. Käsittelevät vain yhtä aihetta per kysymys.
    3. Hyödyntävät sitä, että haastateltava voi miettiä vastausta rauhassa.
    4. Voivat pyytää konkreettisia esimerkkejä tai taustatietoja.
    5. Ovat täysin suomenkielisiä.

    ## OHJEET:
    - Luo yksi kysymys kutakin asiantuntemusaluetta kohden (max 3)
    - Lisää yksi yleinen kysymys
    - Kysymysten tulee olla loogisessa järjestyksessä (tärkein ensin)
    - Käytä sanoja kuten "Analysoi", "Pohdi", "Kuvaile yksityiskohtaisesti"
    - Pyydä tarvittaessa esimerkkejä tai käytännön kokemuksia
    """

        # Pydantic-malli
        # 19.9.2025 CHHANGED THIS BECAUSE PHONE INTERVIEWS HAD PROBLEMS AFTER 2 QUESTIONS
        if interview_type == "call":

            class InterviewQuestionsResponse(BaseModel):
                questions: List[InterviewQuestion] = Field(
                    description="Exactly 2 interview questions for phone interview",
                    min_items=2,
                    max_items=2,
                )

        else:

            class InterviewQuestionsResponse(BaseModel):
                questions: List[InterviewQuestion] = Field(
                    description="List of 2-4 interview questions",
                    min_items=2,
                    max_items=4,
                )

        try:
            structured_llm = self.question_llm.with_structured_output(
                InterviewQuestionsResponse
            )
            response = structured_llm.invoke(prompt_template)

            questions = response.questions
            for i, question in enumerate(questions):
                question.position = i + 1

            if len(questions) < 2:
                raise ValueError("Not enough questions generated")

            return questions[:5]  # max 5

        except Exception as e:
            print(f"⚠️ Error generating questions with LLM: {e}")
            print("   Falling back to template-based questions...")

            # Fallback template-based questions
            questions = []
            for i, area in enumerate(expertise_areas[:3]):
                if language == "fi":
                    question_text = f"Mikä on näkemyksenne asiasta '{focus.lower()}' erityisesti {area.lower()}-näkökulmasta?"
                else:
                    question_text = f"What is your perspective on '{focus.lower()}' specifically from a {area.lower()} viewpoint?"

                questions.append(
                    InterviewQuestion(
                        topic=area,
                        question=question_text,
                        position=i + 1,
                    )
                )

            if len(questions) < 3:
                general_question = (
                    "Onko jotain tärkeää näkökulmaa, joka ei ole vielä tullut julkisuudessa esille?"
                    if language == "fi"
                    else "Is there any important perspective that hasn't been covered in the public discussion yet?"
                )
                questions.append(
                    InterviewQuestion(
                        topic="general",
                        question=general_question,
                        position=len(questions) + 1,
                    )
                )

            return questions


# TEST!
if __name__ == "__main__":
    import os
    import sys
    import json
    from langchain.chat_models import init_chat_model
    from schemas.agent_state import AgentState
    from dotenv import load_dotenv

    load_dotenv()  # Load environment variables from .env file

    print("🧪 TESTING InterviewPlanningAgent with sample data...")
    # RUN WITH THIS:
    # python -m agents.subtask_agents.interview_planning_agent

    interview_method = "phone"  # email # or phone

    print(f"📋 Interview method: {interview_method.upper()}")

    try:
        llm = init_chat_model("gpt-4o-mini", model_provider="openai")
        print("LLM initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize LLM: {e}")
        exit()

    db_dsn = os.getenv("DATABASE_URL")

    # Initialize agent
    agent = InterviewPlanningAgent(llm, db_dsn)

    # Create mock EnrichedArticle
    mock_article = EnrichedArticle(
        article_id="test-article-12345",
        canonical_news_id=66666,
        news_article_id=12345,
        enriched_title="Kauppakeskuksen Sähköakkuhanke Herättää Kysymyksiä Turvallisuudesta",
        enriched_content="""
        # Kauppakeskuksen Sähköakkuhanke Herättää Kysymyksiä Turvallisuudesta
        
        Rovaniemeläinen kauppakeskus Rinteenkulma on hankkinut kiinalaisia Huawei-akkuja puolen miljoonan euron arvosta. 
        Hanke liittyy sähköverkon varajärjestelmiin, mutta herättää kysymyksiä turvallisuudesta.
        
        Kauppakeskuksen johtaja Pekka Rinne kertoo, että akut tulevat osaksi sähköverkon tasapainotusta.
        Fingridin edustaja Mikko Kuivaniemi kommentoi, että tällaisia hankkeita on useita käynnissä.
        
        Kriitikot nostavat esiin huolia kiinalaisten komponenttien turvallisuusriskeistä infrastruktuurissa.
        """,
        published_at="2025-07-28T10:00:00Z",
        source_domain="test-news.fi",
        keywords=["sähköakut", "Huawei", "turvallisuus", "infrastruktuuri"],
        categories=["teknologia", "energia"],
        language="fi",
        summary="Kauppakeskus hankki kiinalaisia akkuja, herättää turvallisuuskysymyksiä",
        contacts=[
            NewsContact(
                name="Pekka Rinne",
                title="Johtaja",
                organization="Kauppakeskus Rinteenkulma",
                email="pekka.rinne@rinteenkulma.fi",
                phone="+358123456789",
                contact_type="source",
                extraction_context="Mentioned as shopping center manager",
                is_primary_contact=True,
            ),
            NewsContact(
                name="Mikko Kuivaniemi",
                title="Päällikkö",
                organization="Fingrid Oyj",
                email="mikko.kuivaniemi@fingrid.fi",
                phone="+358987654321",  # Lisätty puhelinnumero testaukseen
                contact_type="expert",
                extraction_context="Quoted about grid balancing projects",
                is_primary_contact=False,
            ),
        ],
    )

    # Create mock InterviewDecision with selected method
    mock_interview_decision = InterviewDecision(
        interview_needed=True,
        interview_method=interview_method,  # Use selected method
        target_expertise_areas=["energy markets", "cybersecurity", "consumer rights"],
        interview_focus="Investigation of security implications of Chinese technology in critical infrastructure",
        justification="Article lacks balanced perspective on security risks and regulatory oversight of foreign technology in energy infrastructure",
        article_type_influence=f"Given the {'urgency and need for immediate response' if interview_method == 'phone' else 'technical complexity and security concerns'}, {interview_method} interviews {'allow for real-time clarification and emotional nuance' if interview_method == 'phone' else 'allow for detailed expert responses and fact-checking'}",
    )

    # Create mock ReviewedNewsItem
    from schemas.editor_in_chief_schema import (
        ReviewedNewsItem,
        EditorialReasoning,
        ReasoningStep,
        HeadlineNewsAssessment,
    )

    mock_review_result = ReviewedNewsItem(
        status="OK",
        issues=[],
        approval_comment="Article requires additional expert perspectives before publication",
        editorial_reasoning=EditorialReasoning(
            reviewer="editor-in-chief",
            initial_decision="ACCEPT",
            checked_criteria=["Balance", "Security", "Public Interest", "Accuracy"],
            failed_criteria=[],
            reasoning_steps=[
                ReasoningStep(
                    step_id=1,
                    action="Assess need for additional perspectives",
                    observation="Article needs expert views on security implications",
                    result="INFO",
                )
            ],
            explanation="Article accepted but requires expert interviews for balanced coverage",
        ),
        headline_news_assessment=HeadlineNewsAssessment(
            featured=True,
            reasoning="Important infrastructure security topic with broad public interest",
        ),
        interview_decision=mock_interview_decision,
        editorial_decision="interview",
        editorial_warning=None,
    )

    # Create mock state
    mock_state = AgentState()
    mock_state.current_article = mock_article
    mock_state.review_result = mock_review_result

    print("\n📋 TEST INPUT:")
    print(f"   Article: {mock_article.enriched_title}")
    print(f"   Language: {mock_article.language}")
    print(f"   Method: {mock_interview_decision.interview_method}")
    print(
        f"   Target areas: {', '.join(mock_interview_decision.target_expertise_areas)}"
    )
    print(f"   Available contacts: {len(mock_article.contacts)}")

    print("\n🤖 RUNNING AGENT...")

    # Run the agent
    result_state = agent.run(mock_state)

    print("\n📊 TEST RESULTS:")
    if hasattr(result_state, "interview_plan") and result_state.interview_plan:
        plan = result_state.interview_plan
        print(f"   ✅ Interview plan created successfully!")
        print(f"   📅 Method: {plan.interview_method}")

        if plan.email_plan:
            print(f"   📧 Email to: {plan.email_plan.recipient}")
            print(f"   📝 Subject: {plan.email_plan.subject}")
            print(f"   ❓ Questions: {len(plan.email_plan.questions)}")
            print(
                f"   📝 Email ready: {len(plan.email_plan.formatted_email_body)} characters"
            )

            print(f"\n📝 EMAIL QUESTIONS:")
            for q in plan.email_plan.questions:
                print(f"   {q.position}. {q.question}")
                print(f"      Topic: {q.topic}")

            print(f"\n📧 COMPLETE EMAIL PREVIEW:")
            print("=" * 60)
            print(f"To: {plan.email_plan.recipient}")
            print(f"Subject: {plan.email_plan.subject}")
            print("-" * 60)
            print(plan.email_plan.formatted_email_body)
            print("=" * 60)

        elif plan.phone_plan:
            print(f"   📞 Phone to: {plan.phone_plan.to_number}")
            if plan.phone_plan.from_number:
                print(f"   📞 From number: {plan.phone_plan.from_number}")

            # Hae tiedot phone_script_json:sta
            script_json = plan.phone_plan.phone_script_json
            questions_data = script_json.get("questions_data", [])

            print(f"   🎙️ Language: {script_json.get('language', 'fi')}")
            print(f"   ❓ Questions: {len(questions_data)}")
            print(f"   🎯 Interview focus: {script_json.get('interview_focus', 'N/A')}")
            print(f"   📝 Script ready: {len(str(script_json))} characters")

            print(f"\n📝 PHONE INTERVIEW QUESTIONS:")
            for q in questions_data:
                print(
                    f"   {q.get('position', '?')}. {q.get('text', q.get('question', 'No question text'))}"
                )
                print(f"      📋 Topic: {q.get('topic', 'No topic')}")
                if q.get("follow_up_suggestions"):
                    print(
                        f"      🔄 Follow-ups: {len(q['follow_up_suggestions'])} suggestions"
                    )

            print(f"\n🎤 PHONE SCRIPT DETAILS:")
            print(
                f"   🎯 Target contact: {script_json.get('contact_info', {}).get('name', 'Unknown')}"
            )
            print(
                f"   🏢 Organization: {script_json.get('contact_info', {}).get('organization', 'Unknown')}"
            )
            print(
                f"   📞 Phone: {script_json.get('contact_info', {}).get('to_number', plan.phone_plan.to_number)}"
            )

            # Näytä avainkohdat skriptistä
            if script_json.get("opening_statement"):
                print(f"\n📖 OPENING STATEMENT:")
                print(f"   {script_json['opening_statement'][:200]}...")

            if script_json.get("closing_statement"):
                print(f"\n🎬 CLOSING STATEMENT:")
                print(f"   {script_json['closing_statement'][:150]}...")

            print(f"\n📜 FULL PHONE SCRIPT JSON:")
            print("=" * 80)
            print(json.dumps(script_json, ensure_ascii=False, indent=2))
            print("=" * 80)

        print(f"\n👥 AVAILABLE CONTACTS:")
        for i, contact in enumerate(plan.available_contacts, 1):
            print(f"   {i}. {contact.name} ({contact.title}) - {contact.contact_type}")
            if contact.email:
                print(f"      📧 Email: {contact.email}")
            if contact.phone:
                print(f"      📞 Phone: {contact.phone}")
            print(f"      🏢 Organization: {contact.organization}")
            if contact.is_primary_contact:
                print(f"      ⭐ Primary contact")
    else:
        print("   ❌ No interview plan created!")
        print(
            f"   State has interview_plan attribute: {hasattr(result_state, 'interview_plan')}"
        )
        if hasattr(result_state, "interview_plan"):
            print(f"   interview_plan value: {result_state.interview_plan}")

    print("\n🎯 Test completed - InterviewPlanningAgent ready for production use!")
