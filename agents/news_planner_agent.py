# File: agents/news_planner_agent.py

import sys
import os
import datetime

from schemas.article_plan_schema import NewsArticlePlan

# Add the project root to the Python path to allow for absolute imports
# This is necessary for the standalone test runner to find the 'agents' and 'schemas' modules.
# SO THE LINE BELOW IS JUST FOR TESTING PURPOSES
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.feed_schema import CanonicalArticle
from typing import List


NEWS_PLANNING_PROMPT = """
You are a methodical assistant news editor. Your task is to analyze the given news article and create a coherent plan to enrich it by thinking step-by-step.
The original language of the article is '{language}'.
The article was originally published on: {published_at}.
The current date is: {current_date}.

**Thinking Process:**
1.  **Analyze Content:** First, read the original article to understand its core subject and its context based on its publication date.
2.  **Derive Keywords & Categories:** Based on the analysis, identify the most relevant keywords and broader categories.
3. **Formulate Diverse & Timely Search Queries:** Using the keywords and categories, create 2-3 specific Google search queries. Formulate queries that cover different angles: * **Follow-up:** What has happened since the article was published?
4.  **Finalize Plan:** Finally, formulate a new headline and a brief summary.

Please provide the final output in the required structured format.
Limit amount of queries to 3, so make them as good as possible.

**Original Article:**
---
{article_text}
---
"""


class NewsPlannerAgent(BaseAgent):
    """An agent that uses an LLM to create a plan for enriching a news article."""

    def __init__(self, llm):
        super().__init__(llm=llm, prompt=None, name="NewsPlannerAgent")
        self.structured_llm = self.llm.with_structured_output(NewsArticlePlan)

    def run(self, state: AgentState) -> AgentState:
        print("NewsPlannerAgent: Starting to plan enrichment for articles...")

        # Käytä suoraan state.articles - nyt tyyppi on oikea!
        articles = state.articles
        if not articles:
            print("NewsPlannerAgent: No articles to plan.")
            return state

        print(f"NewsPlannerAgent: Planning enrichment for {len(articles)} articles...")

        # Tyypitetty lista
        article_plans: List[NewsArticlePlan] = []

        for art in articles:
            print(f"\n  - Planning for: {art.link}")

            # LLMs want time as year-month-day format
            published_date_str = art.published_at or "unknown"
            print(f"    - Published date: {published_date_str}")
            print(f"    - current_date: {datetime.datetime.now().strftime('%Y-%m-%d')}")

            prompt_content = NEWS_PLANNING_PROMPT.format(
                article_text=art.content,
                language=art.language or "fi",  # Käytä suoraan art.language
                published_at=published_date_str,
                current_date=datetime.datetime.now().strftime("%Y-%m-%d"),
            )

            try:
                # Suoraan LLM:stä NewsArticlePlan objektiksi
                plan = self.structured_llm.invoke(prompt_content)

                # Käytä unique_id:tä tunnistamiseen
                plan.article_id = (
                    art.unique_id or art.link
                )  # Fallback URL:iin jos unique_id puuttuu

                article_plans.append(plan)

            except Exception as e:
                print(f"Error processing article {art.link} with LLM: {e}")
                continue

        # Tallennetaan suunnitelmat plan-kenttään - alkuperäiset artikkelit jäävät koskemattomiksi
        state.plan = article_plans
        print("NewsPlannerAgent: Done.")
        return state


if __name__ == "__main__":
    from dotenv import load_dotenv
    from langchain.chat_models import init_chat_model

    # RUN with this command:
    # python -m agents.news_planner_agent

    # Load environment variables for API keys
    load_dotenv()

    # Initialize the Language Model
    try:
        llm = init_chat_model("gpt-4o-mini", model_provider="openai")
        print("LLM initialized successfully.")
    except Exception as e:
        print(
            f"Failed to initialize LLM. Make sure your API keys are set in .env file. Error: {e}"
        )
        exit()

    # Create mock data using the correct CanonicalArticle schema
    test_articles = [
        CanonicalArticle(
            link="http://test.com/article1",
            title="Finnish government to boost tech sector",
            content="""The Finnish government has announced a new initiative to boost the country's technology sector.
            The plan includes significant investments in artificial intelligence research and development centers across Finland.
            Minister of Economic Affairs, Mika Lintilä, stated that the goal is to make Finland a leading hub for AI innovation in Europe.""",
            language="en",
            contacts=[],  # No contacts for this article
            article_type="news",
            published_at="2024-06-15",
        ),
        CanonicalArticle(
            link="http://test.fi/uutinen2",
            title="Tangomarkkinat valmistelut käynnissä",
            content="""Seinäjoen kaupunki valmistautuu ensi viikolla alkaviin Tangomarkkinoihin. Tapahtumaan odotetaan kymmeniä tuhansia kävijöitä.
            Keskustan liikennejärjestelyihin on tulossa muutoksia, ja lisävuoroja on luvassa julkiseen liikenteeseen.
            Poliisi muistuttaa festivaalivieraita varovaisuudesta ja omaisuuden suojaamisesta.""",
            language="fi",
            contacts=[
                {
                    "name": "Maija Malli",
                    "title": "Press Officer",
                    "organization": "Tangomarkkinat ry",
                    "email": "maija.malli@testi.fi",
                    "phone": "+358123456789",
                    "contact_type": "spokesperson",
                    "extraction_context": "Mentioned in press release",
                    "is_primary_contact": True,
                }
            ],  # Add a mock contact for this press release
            article_type="press_release",
        ),
    ]
    print(
        f"Created {len(test_articles)} mock articles for testing using the correct CanonicalArticle schema."
    )

    # Initialize the Agent
    planner_agent = NewsPlannerAgent(llm=llm)

    # Prepare the initial state
    initial_state = AgentState(articles=test_articles)

    # Run the agent
    print("\n--- Invoking the agent's run method... ---")
    result_state = planner_agent.run(initial_state)
    print("--- Agent run completed. ---")

    # Print the results
    # -> we should have a plan for web searches, categories, keywords, etc...
    print("\n--- Results ---")
    if result_state.plan:
        print(f"Created {len(result_state.plan)} article plans")
        for i, plan in enumerate(result_state.plan):
            # ✅ KORJAUS: Käytä objektin attribuutteja, ei dict-avainia
            print(f"\n--- Plan for Article {i+1} ({plan.article_id}) ---")
            print(f"  Headline: {plan.headline}")
            print(f"  Summary: {plan.summary}")
            print(f"  Keywords: {plan.keywords}")
            print(f"  Categories: {plan.categories}")
            print(f"  Search Queries: {plan.web_search_queries}")
    else:
        print("No article plans were created.")

# Agent flow (before and after):
# ... article_content_extractor_agent -> news_storer_agent -> NEWS_PLANNER_AGENT (WE ARE HERE) -> WebSearchAgent -> ...
