from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState, InterviewAgentState
from schemas.enriched_article import EnrichedArticle, EnrichedArticleWithInterview
from schemas.interview_schema import (
    DataAfterInterviewFromDatabase,
    InterviewPlan,
)
from pydantic import BaseModel, Field
from typing import Optional

# Simplified Article Enrichment Prompt
ARTICLE_ENRICHMENT_PROMPT = """
You are an experienced journalist responsible for enriching articles with interview content.

You have been given:
1. An original article that needed additional perspectives
2. Raw interview content from an expert source
3. Information about the expert who provided the content

**Expert Information:**
- Name: {respondent_name}
- Title: {respondent_title}
- Organization: {respondent_organization}

Your task is to create an enriched version of the article that integrates the interview content to provide better balance, expert perspectives, and journalistic depth.

## ORIGINAL ARTICLE:

**Content:**
{article}

## INTERVIEW CONTENT:

**Interview (questions and answers):**
{interview}

## ENRICHMENT GUIDELINES:

### TITLE HANDLING:
- **Do not modify the title too much (or at all)**
- Keep the original title's core message and structure intact
- Avoid adding expert names or interview references to the title
- Only make minimal adjustments if absolutely necessary for clarity

### INTEGRATION STRATEGY:
1. **Preserve original structure** - Enhance existing content, don't completely rewrite
2. **Extract key insights** - Identify the most valuable quotes and insights from the interview content
3. **Strategic placement** - Add expert perspectives that support, challenge, or expand key points
4. **Maintain journalistic tone** - Keep the original article's style and language ({language})
5. **Expert attribution** - Properly credit the source with title and organization

### CONTENT ENHANCEMENT:
- Parse the interview content to find relevant quotes and insights
- Integrate expert perspectives that weren't in the original article
- Add context and explanations that strengthen the story
- Address gaps identified in the original editorial review
- Ensure all additions provide genuine journalistic value

### EXPERT ATTRIBUTION:
- **First mention**: Introduce the expert with full credentials: "{respondent_name}, {respondent_title}, {respondent_organization}"
- Ensure expert credentials add credibility to quotes and insights
- Format attribution consistently throughout the article

### QUALITY FOCUS:
- Enrichment over expansion - focus on quality insights, not just length
- Use expert credentials appropriately to add credibility
- Ensure smooth integration - new content should flow naturally
- Every addition should serve the reader and strengthen the story

## ENRICHED ARTICLE:

Create an enriched version of the article that strategically integrates the interview content while maintaining the original article's core message and journalistic integrity.
"""


class EnrichedArticleResult(BaseModel):
    """Result of article enrichment process."""

    enriched_title: str = Field(description="Enriched article title")
    enriched_content: str = Field(description="Complete enriched article content")
    enrichment_summary: str = Field(description="Summary of what was enriched")
    respondent_name: str = Field(description="Name of expert source integrated")


class ArticleEnricherAgent(BaseAgent):
    """Agent that enriches articles with raw interview content."""

    def __init__(self, llm, db_dsn: str):
        super().__init__(
            llm=llm, prompt=ARTICLE_ENRICHMENT_PROMPT, name="ArticleEnricherAgent"
        )
        self.db_dsn = db_dsn
        self.structured_llm = llm

    def run(self, state: InterviewAgentState) -> AgentState:
        """Enriches article with raw interview content."""
        print("ArticleEnricherAgent: Enriching article with interview content...")

        if not hasattr(state, "current_article") or not state.current_article:
            print("ArticleEnricherAgent: No current_article to enrich!")
            return state

        article: DataAfterInterviewFromDatabase = state.current_article
        # support both raw_interview_content and interview_content
        interview: str = getattr(state, "raw_interview_content", None) or getattr(
            state, "interview_content", ""
        )

        try:
            # Build prompt with current article and interview content
            article_text = getattr(article, "enriched_content", "")
            language = getattr(article, "language", "fi")

            # Get contact information from state
            respondent_name = getattr(
                state, "interview_respondent_name", "Unknown Expert"
            )
            respondent_title = (
                getattr(state, "interview_respondent_title", "") or "Expert"
            )
            respondent_organization = (
                getattr(state, "interview_respondent_organization", "") or "Independent"
            )

            prompt_text = self.prompt.format(
                article=article_text,
                interview=interview,
                language=language,
                respondent_name=respondent_name,
                respondent_title=respondent_title,
                respondent_organization=respondent_organization,
            )

            # LLM: structured output for EnrichedArticleWithInterview
            structured_llm = self.structured_llm.with_structured_output(
                EnrichedArticleWithInterview
            )
            response = structured_llm.invoke(prompt_text)
            print("LLM RESPONSE:", response)

            # Set result into declared field for downstream integration
            state.new_enriched_article = EnrichedArticleWithInterview(
                enriched_title=getattr(response, "enriched_title", ""),
                enriched_content=getattr(response, "enriched_content", ""),
                summary=getattr(
                    response, "summary", getattr(response, "enrichment_summary", "")
                ),
            )

            return state

        except Exception as e:
            print(f"Error enriching article: {e}")
            import traceback

            traceback.print_exc()
            return state


# TEST RUNNER
if __name__ == "__main__":
    import os
    from langchain.chat_models import init_chat_model
    from schemas.agent_state import AgentState
    from dotenv import load_dotenv
    import json

    load_dotenv()

    print("TESTING ArticleEnricherAgent (SIMPLIFIED)...")

    try:
        llm = init_chat_model("gpt-4o-mini", model_provider="openai")
        print("LLM initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize LLM: {e}")
        exit()

    db_dsn = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/newsdb")

    # Initialize agent
    agent = ArticleEnricherAgent(llm, db_dsn)

    # Create mock article
    mock_article = DataAfterInterviewFromDatabase(
        article_id=12345,
        enriched_title="Kauppakeskuksen Sähköakkuhanke Herättää Kysymyksiä Turvallisuudesta",
        enriched_content="""
# Kauppakeskuksen Sähköakkuhanke Herättää Kysymyksiä Turvallisuudesta

Rovaniemeläinen kauppakeskus Rinteenkulma on hankkinut kiinalaisia Huawei-akkuja puolen miljoonan euron arvosta. 
Hanke liittyy sähköverkon varajärjestelmiin, mutta herättää kysymyksiä turvallisuudesta.

Kauppakeskuksen johtaja Pekka Rinne kertoo, että akut tulevat osaksi sähköverkon tasapainotusta.
Fingridin edustaja Mikko Kuivaniemi kommentoi, että tällaisia hankkeita on useita käynnissä.

Kriitikot nostavat esiin huolia kiinalaisten komponenttien turvallisuusriskeistä infrastruktuurissa.
        """,
        language="fi",
    )

    # Test with email content
    email_content = """
Hei,

Kiitos kysymyksistänne. Vastaan mielelläni:

Turvallisuusriskeistä: Kiinalaisten akkujärjestelmien käyttö infrastruktuurissa vaatii huolellista riskinarviointia. Teknologia on laadukasta, mutta geopoliittiset näkökohdat on otettava huomioon kriittisessä infrastruktuurissa.

Sähköverkon toiminnasta: Akkujärjestelmät tarjoavat nopeaa säätövoimaa ja parantavat verkon vakautta. Huawein teknologia on teknisesti korkealaatuista ja soveltuu kaupallisiin sovelluksiin.

Ystävällisin terveisin,
Dr. Marja Kyberturva
    """

    print("\nTEST INPUT:")
    print(f"   Original article: {len(mock_article.enriched_content)} characters")
    print(f"   Email content: {len(email_content)} characters")

    # Test with email content
    print("\nTESTING WITH EMAIL CONTENT:")
    mock_state = InterviewAgentState()
    mock_state.current_article = mock_article
    mock_state.interview_content = email_content
    mock_state.interview_respondent_name = "Dr. Marja Kyberturva"
    mock_state.interview_respondent_title = "Kyberturvallisuusasiantuntija"
    mock_state.interview_respondent_organization = "Huoltovarmuuskeskus"

    result_state = agent.run(mock_state)

    if (
        hasattr(result_state, "new_enriched_article")
        and result_state.new_enriched_article
    ):
        result = result_state.new_enriched_article
        print(f"   Email enrichment successful!")
        print(f"   Enhanced title: {result.enriched_title[:80]}...")
        print(
            f"   Summary: {result.summary[:100] if result.summary else 'No summary'}..."
        )
        print(f"   Content length: {len(result.enriched_content)} characters")
    else:
        print("   Email enrichment failed!")

    print("\nTest completed - ArticleEnricherAgent ready!")
    print("\nKEY FEATURES:")
    print("   - Handles raw interview content (email body, phone JSON, anything)")
    print("   - Uses contact information from news_contacts table")
    print("   - Proper expert attribution with title and organization")
    print("   - Simple state interface with InterviewAgentState")
    print("   - Quality focus - enrichment over expansion")
    print("   - Maintains original article structure and style")
