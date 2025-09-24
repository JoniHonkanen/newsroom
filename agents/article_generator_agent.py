# File: agents/article_generator_agent.py

import sys
import os
import datetime
from typing import List, Dict, Optional

# Add the project root to the Python path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.feed_schema import CanonicalArticle
from schemas.article_plan_schema import NewsArticlePlan
from schemas.parsed_article import ParsedArticle
from schemas.enriched_article import EnrichedArticle, ArticleReference, LLMArticleOutput


ARTICLE_GENERATION_PROMPT = """
You are an expert news editor and content creator. Your task is to create an enriched version of a news article by combining the original article with additional web search results.

**Original Article Information:**
- Content: {original_content}
- Published: {published_at}
- Language: {language}

**Plans for Enrichment:**
- Keywords: {planned_keywords}
- Categories: {planned_categories}

**Web Search Results:**
{web_search_results}

**Your Task:**
1. Create a completely new news article using the original article as your primary source, then enrich it with additional information from web search results.
2. Maintain the same language as the original article ({language}), this is important!
3. Write in a professional, journalistic style that matches the original tone.
4. Write for your target audience - make the story relevant and accessible to general readers.
5. Identify the key angle that makes this story important to readers - what's the main point they should understand?
6. Create a clear, informative headline that:
    - Captures the main news event or development
    - Is specific and factual, not vague or clickbait
    - Uses active voice and strong verbs when possible
    - Is compelling enough to encourage reading
7. Use the web search results to add depth, context, background information, and new perspectives to the story.
8. Structure the article with appropriate headings, paragraphs, and a logical flow.
9. Keep the enriched content comprehensive but concise, with a focus on quality over quantity.
10. Make sure to maintain factual accuracy and journalistic integrity.
11. Rewrite the story completely in your own words while preserving all important facts and the core narrative.
12. Start with the most newsworthy information first (inverted pyramid structure).
13. Include relevant background context that helps readers understand the significance of the story.
14. Ensure all claims are factual and can be supported by the provided sources.

**CRITICAL - What NOT to include:**
- Do NOT include any contact information (phone numbers, emails, addresses)
- Do NOT include "breaking news updates", "story developing", or "more updates to follow" type statements
- Do NOT include calls for tips like "Do you know something about this? Tell us"
- Do NOT include journalist names, bylines, or editorial notes
- Do NOT include publication-specific elements like "Subscribe to our newsletter"
- Do NOT include press release boilerplate text or media instructions
- Do NOT copy sentences directly from the original - always rewrite in your own words
- Do NOT include metadata sections like "Keywords:" or "Image suggestions:" in the article content
    - These belong only in the structured output fields, not in the readable article
- Focus ONLY on the factual news content itself

**IMPORTANT - Image Placeholders:**
15. Include strategic image placeholders in your markdown:
   - ONE hero/main image at the very beginning: ![main topic](PLACEHOLDER_IMAGE)
   - ONE supporting image after the first paragraph: ![descriptive alt text](PLACEHOLDER_IMAGE)  
   - 0-1 additional images at natural break points (before major subheadings)
   **NOTE:** The main image must be placed **after the main heading**, not before it.
   
16. For alt text, use SHORT, specific search terms (max 1-3 words):
   - ALWAYS use simple English terms even for Finnish articles (better image search results)
   - Avoid special characters, use only: letters, spaces, basic words

17. In image_suggestions, provide 1-3 SHORT search terms that represent what the article is actually about. First understand the main topic of the article and the specific things it discusses, then choose images that match that topic.

Examples:
- ![finnish parliament](PLACEHOLDER_IMAGE)
- ![ai research](PLACEHOLDER_IMAGE)  
- ![business handshake](PLACEHOLDER_IMAGE)

Produce a fully formatted article in markdown format, ready for publication.
"""


class ArticleGeneratorAgent(BaseAgent):
    """An agent that generates enriched news articles by combining original content with web search results."""

    def __init__(self, llm):
        super().__init__(llm=llm, prompt=None, name="ArticleGeneratorAgent")
        self.structured_llm = self.llm.with_structured_output(LLMArticleOutput)

    def _find_original_article(
        self, article_id: str, articles: List[CanonicalArticle]
    ) -> Optional[CanonicalArticle]:
        """Find the original article by its unique_id or link."""
        for article in articles:
            if (article.unique_id and article.unique_id == article_id) or (
                article.link == article_id
            ):
                return article
        return None

    def _format_web_search_results(self, results: List[ParsedArticle]) -> str:
        """Format web search results for the prompt."""
        if not results:
            return "No relevant web search results were found."

        formatted_results = []

        for i, result in enumerate(results, 1):
            article_section = f"--- Search Result {i} ---\n"
            article_section += f"Source: {result.domain}\n"

            if result.markdown:
                max_content_length = 2000
                content = (
                    result.markdown[:max_content_length] + "...[content truncated]"
                    if len(result.markdown) > max_content_length
                    else result.markdown
                )
                article_section += f"Content:\n{content}\n"

            article_section += f"--- End of Search Result {i} ---\n"
            formatted_results.append(article_section)

        return "\n\n".join(formatted_results)

    def run(self, state: AgentState) -> AgentState:
        """Runs the article generator agent on the provided state."""
        print("ArticleGeneratorAgent: Starting to generate enriched articles...")
        articles = state.articles

        plans = state.plan or []
        article_search_map = state.article_search_map
        canonical_ids = state.canonical_ids

        if not articles or not plans:
            print("ArticleGeneratorAgent: No articles or plans to work with.")
            return state

        print(
            f"ArticleGeneratorAgent: Generating enriched articles for {len(plans)} plans..."
        )

        enriched_articles: List[EnrichedArticle] = []

        for plan in plans:
            article_id = plan.article_id
            print(f"\n  - Generating enriched article for: {article_id}")

            # Find the original article
            original_article = self._find_original_article(article_id, articles)
            if not original_article:
                print(
                    f"    - Original article not found for ID: {article_id}. Skipping."
                )
                continue

            # Get canonical ID
            canonical_news_id = canonical_ids.get(article_id)
            if canonical_news_id:
                print(f"    - Using canonical_news_id: {canonical_news_id}")

            # Get web search results for this article
            web_search_results = article_search_map.get(article_id, [])
            print(
                f"    - Found {len(web_search_results)} web search results for this article"
            )

            # Format web search results
            formatted_results = self._format_web_search_results(web_search_results)

            # Prepare the prompt
            prompt_content = ARTICLE_GENERATION_PROMPT.format(
                original_content=original_article.content or "",
                published_at=original_article.published_at
                or "Unknown publication date",
                language=original_article.language or "en",
                planned_keywords=", ".join(plan.keywords),
                planned_categories=", ".join(plan.categories),
                web_search_results=formatted_results,
            )

            try:
                # Generate using the simplified schema
                llm_output = self.structured_llm.invoke(prompt_content)

                # Create references from web search results
                article_references = []

                # Add original article as reference
                if original_article.link:
                    original_ref = ArticleReference(
                        title=original_article.title,
                        url=str(original_article.link),
                    )
                    article_references.append(original_ref)

                # Add web search results as references
                for result in web_search_results:
                    if (
                        result.url
                        and result.markdown
                        and len(result.markdown.strip()) > 50
                    ):
                        new_ref = ArticleReference(
                            title=f"Content from {result.domain}",
                            url=result.url,
                        )
                        article_references.append(new_ref)

                published_at_str = ""
                if original_article.published_at:
                    if isinstance(original_article.published_at, str):
                        published_at_str = original_article.published_at
                    else:
                        # Muunna datetime-objekti merkkijonoksi
                        published_at_str = original_article.published_at.isoformat()

                # Create the complete EnrichedArticle
                enriched_article = EnrichedArticle(
                    article_id=article_id,
                    canonical_news_id=canonical_news_id,
                    enriched_title=llm_output.enriched_title,
                    enriched_content=llm_output.enriched_content,
                    published_at=published_at_str,
                    source_domain=original_article.source_domain or "",
                    keywords=llm_output.keywords,
                    categories=plan.categories if hasattr(plan, "categories") else [],
                    language=original_article.language or "en",
                    sources=[
                        result.url
                        for result in web_search_results
                        if hasattr(result, "url")
                    ],
                    references=article_references,
                    locations=llm_output.locations,
                    summary=llm_output.summary,
                    enrichment_status="success",
                    original_article_type=original_article.article_type,
                    contacts=original_article.contacts,
                    image_suggestions=llm_output.image_suggestions,
                )

                enriched_articles.append(enriched_article)
                print(f"    - Successfully generated enriched article")

            except Exception as e:
                print(f"    - Error generating enriched article: {e}")

        state.enriched_articles = enriched_articles
        return state


if __name__ == "__main__":
    from dotenv import load_dotenv
    from langchain.chat_models import init_chat_model
    import datetime

    # GOAL -> Enriched articles
    # So this combine original article with web search results (articles), trying to enrich the original article with new information.
    # Here we can see that we have CanonicalArticle as the original article, and ParsedArticle as the web search results.

    # RUN WITH THIS COMMAND:
    # python -m agents.article_generator_agent

    print("--- Running ArticleGeneratorAgent in isolation for testing ---")
    load_dotenv()

    # Initialize the LLM
    try:
        llm = init_chat_model("gpt-4o-mini", model_provider="openai")
        print("LLM initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize LLM: {e}")
        exit()

    # Create test data - Original article
    test_article = CanonicalArticle(
        title="Finland's AI Strategy Update",
        link="http://test.fi/suomi-ai-strategy",
        unique_id="test-finland-ai-2024",
        content="""Finland has announced new initiatives to strengthen its artificial intelligence capabilities. 
        The government plans to invest 50 million euros in AI research centers across the country. 
        These centers will focus on healthcare AI, autonomous systems, and sustainable technology solutions.""",
        published_at="2024-06-15",
        language="en",
        source_domain="test.fi",
        article_type="news",
        contacts=[],
    )

    # Create test plan (NewsArticlePlan object)
    # This test really dont use this plan (it was agent before this)... but lets have it just for example here
    test_plan = NewsArticlePlan(
        article_id="test-finland-ai-2024",
        headline="Finland Expands AI Leadership with Major Investment",
        summary="Finland strengthens its AI position with significant funding",
        keywords=["Finland", "AI", "investment", "research", "technology"],
        categories=["Technology", "Politics", "Innovation"],
        web_search_queries=[
            "Finland AI strategy 2024",
            "Nordic countries artificial intelligence investment",
            "European Union AI research funding",
        ],
    )

    # Create mock web search results
    test_web_results = [
        ParsedArticle(
            markdown="""# Finland's AI Investment Grows
            
Finland has committed to becoming a European leader in artificial intelligence. The new funding will support:

- Three new AI research centers in Helsinki, Tampere, and Oulu
- Partnerships with major tech companies like Nokia and Rovio
- International collaboration with MIT and Stanford University
- Focus on ethical AI development and privacy protection

The initiative is part of Finland's broader digitalization strategy.""",
            domain="techcrunch.com",
            url="https://techcrunch.com/finland-ai-investment",
        ),
        ParsedArticle(
            markdown="""# Nordic AI Collaboration

The Nordic countries are pooling resources for AI research. Finland leads this initiative with:

- Shared research databases
- Cross-border talent exchange programs  
- Joint funding for AI startups
- Common ethical AI guidelines

This collaboration positions the Nordic region as a global AI hub.""",
            domain="reuters.com",
            url="https://reuters.com/nordic-ai-collaboration",
        ),
    ]

    # Create mock AgentState using the correct schema
    from schemas.agent_state import AgentState

    initial_state = AgentState(
        articles=[test_article],
        plan=[test_plan],
        article_search_map={"test-finland-ai-2024": test_web_results},
        canonical_ids={"test-finland-ai-2024": 123},
        enriched_articles=[],
    )

    print(f"\nTest setup:")
    print(f"- Articles: {len(initial_state.articles)}")
    print(f"- Plans: {len(initial_state.plan)}")
    print(
        f"- Search results: {len(initial_state.article_search_map.get('test-finland-ai-2024', []))}"
    )
    print(f"- Test plan ID: {initial_state.plan[0].article_id}")

    # Create and run the agent
    generator_agent = ArticleGeneratorAgent(llm)

    print("\n--- Invoking the agent's run method... ---")
    result_state = generator_agent.run(initial_state)
    print("--- Agent run completed. ---")

    # Print results
    print("\n--- Results ---")
    if result_state.enriched_articles:
        print(f"Generated {len(result_state.enriched_articles)} enriched articles")

        for i, article in enumerate(result_state.enriched_articles):
            print(f"\n--- Enriched Article {i+1} ---")
            print(f"  Article ID: {article.article_id}")
            print(f"  Canonical ID: {article.canonical_news_id}")
            print(f"  Title: {article.enriched_title}")
            print(f"  Language: {article.language}")
            print(f"  Keywords: {article.keywords}")
            print(f"  Categories: {article.categories}")
            print(f"  Sources: {len(article.sources)} sources")
            print(f"  References: {len(article.references)} references")
            print(f"  Status: {article.enrichment_status}")
            print(f"  Full content:\n{article.enriched_content}")

            if article.locations:
                print(f"  Locations: {len(article.locations)} locations found")
                for loc in article.locations[:2]:  # Show first 2 locations
                    # LocationTag on Pydantic objekti, ei dict - käytä attribuutteja
                    city = getattr(loc, "city", None) or "Unknown"
                    country = getattr(loc, "country", None) or "Unknown"
                    print(f"    - {city}, {country}")

        print(f"\n--- State validation ---")
        print(f"Original articles: {len(initial_state.articles)}")
        print(f"Original plans: {len(initial_state.plan)}")
        print(f"Result enriched articles: {len(result_state.enriched_articles)}")
        print(f"Canonical IDs preserved: {len(result_state.canonical_ids)}")

    else:
        print("No enriched articles were generated")
        print("Check for errors in the agent execution above")

# Agent flow (before and after):
# ... -> web_search_agent -> ARTICLE_GENERATOR_AGENT (WE ARE HERE) -> article_image_generator_agent -> ...
