from typing import List, Optional  # Korjattu import - ei ast.List!
from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from langdetect import detect, LangDetectException  # type: ignore
from schemas.parsed_article import ParsedArticle
from schemas.feed_schema import CanonicalArticle
from services.article_parser import to_structured_article


class ArticleContentExtractorAgent(BaseAgent):
    """Agent that fetches articles."""

    def __init__(self):
        super().__init__(llm=None, prompt=None, name="ArticleContentExtractorAgent")
        # we want to detect if this is article or press release
        # THIS WILL PROBABLY NEED BETTER LOGIC IN THE FUTURE!!!
        self.PRESS_RELEASE_URL_KEYWORDS = [
            "/tiedotteet",
            "/tiedote/",
            "/press-releases",
            "/media/",
            "/newsroom/",
        ]
        self.PRESS_RELEASE_TITLE_KEYWORDS = [
            "tiedote:",
            "lehdistötiedote",
            "press release:",
            "mediatiedote",
        ]
        self.PRESS_RELEASE_CONTENT_KEYWORDS = {
            "contact_info": ["lisätietoja:", "for more information:", "yhteystiedot:"],
            "distributors": [
                "koodiviidakko",
                "cision",
                "stt info",
                "epressi",
                "meltwater",
            ],
        }

    def _classify_article_type(self, url: str, title: str, content: str) -> str:
        """
        Classifies article as 'news' or 'press_release' based on URL, title, and content heuristics.
        Maybe we can use different kind of agent to do something based on this classification.
        """
        # For press releases, its more important to do interviews...
        # thats why we need to classify them
        lower_url = url.lower()
        lower_title = title.lower()
        # We only check the last 300 characters, because the end of the article often contains contact information or distribution details.
        content_ending = content.lower()[-300:]

        # check if the URL contains known press release keywords
        for keyword in self.PRESS_RELEASE_URL_KEYWORDS:
            if keyword in lower_url:
                return "press_release"

        # check if the title contains known press release keywords
        for keyword in self.PRESS_RELEASE_TITLE_KEYWORDS:
            if lower_title.startswith(keyword):
                return "press_release"

        # check if the content ending contains known press release keywords
        for keyword in self.PRESS_RELEASE_CONTENT_KEYWORDS["contact_info"]:
            if keyword in content_ending:
                return "press_release"

        # if none of the earlier checks matched, classify as news
        return "news"

    def _detect_language(self, text: Optional[str]) -> Optional[str]:
        """Try to detect the language of the given text."""
        if not text:
            return None
        try:
            return detect(text)
        except LangDetectException:
            return None

    def run(self, state: AgentState) -> AgentState:
        # Käytä suoraan state.articles - nyt tyyppi on oikea!
        articles = state.articles
        if not articles:
            print("ArticleContentExtractorAgent: No new articles to process.")
            return state

        print(
            f"ArticleContentExtractorAgent: Fetching content for {len(articles)} articles..."
        )
        handled_articles: List[CanonicalArticle] = []

        for art in articles:
            url = art.link
            if not url:
                print("No URL found for article, skipping.")
                continue
            # This function fetches the article content and returns a structured representation
            # this includes parsing html elements and converting them to markdown
            # Contacts are now extracted by ContactsExtractorAgent in the main pipeline
            structured: ParsedArticle = to_structured_article(url, check_contact=False)
            if structured is None:
                print(f"Failed to fetch article content: {url}")
                continue

            # Check the language of the article using its title
            language = self._detect_language(art.title)

            # News or press release?
            article_type = self._classify_article_type(
                url, art.title, structured.markdown
            )

            # Combine the original article fields with the new structure (you can keep the summary, etc.)
            single_article: CanonicalArticle = art.model_copy(
                update={
                    "content": structured.markdown,
                    "published_at": structured.published
                    or art.published_at,  # fallback!
                    "source_domain": structured.domain,
                    "language": language,
                    "article_type": article_type,
                    # Do not set contacts here; handled by ContactsExtractorAgent
                }
            )

            handled_articles.append(single_article)

        # Update the state with the processed articles, articles will be list of CanonicalArticle objects
        # Like this: state.articles = [CanonicalArticle]
        state.articles = handled_articles
        print("ArticleContentExtractorAgent: Done.")
        return state


if __name__ == "__main__":
    from schemas.agent_state import AgentState
    from schemas.feed_schema import CanonicalArticle
    from schemas.parsed_article import ParsedArticle
    from agents.article_content_extractor_agent import ArticleContentExtractorAgent

    # Run with this commmand:
    # python -m agents.article_content_extractor_agent

    # Mockataan yksi CanonicalArticle
    mock_article = CanonicalArticle(
        unique_id="yle-123",
        title="Testiuutinen: Tekoäly mullistaa journalismia",
        link="https://yle.fi/uutiset/3-12345678",
        published_at="2025-07-30T10:00:00Z",
        summary="Tekoäly muuttaa uutistuotantoa Suomessa.",
        source_domain="yle.fi",
        language="fi",
        article_type="news",
        contacts=[],  # this article should not have contacts
        content="",
    )

    mock_article_2 = CanonicalArticle(
        unique_id="epressi-1",
        title="Grillin voi puhdistaa ekologisesti sipulilla tai erikoistahnalla",
        link="https://www.epressi.com/tiedotteet/lifestyle/grillin-voi-puhdistaa-ekologisesti-sipulilla-tai-erikoistahnalla.html",
        published_at="2025-07-30T13:00:00Z",
        summary="Ekologinen grillin puhdistus onnistuu sipulilla tai erikoistahnalla.",
        source_domain="epressi.com",
        language="fi",
        article_type="press_release",
        contacts=[],  # this article should have contacts
        content="",
    )

    # So this test should handle both news and press release articles
    # Other should have contacts, other not
    state = AgentState(articles=[mock_article, mock_article_2])

    # Luo agentti
    agent = ArticleContentExtractorAgent()

    print("🧪 Testataan ArticleContentExtractorAgentia mock-artikkelilla...")
    result_state = agent.run(state)

    print("\nTestin tulokset:")
    for i, article in enumerate(result_state.articles, 1):
        print(f"{i}. {article.title}")
        print(f"   Linkki: {article.link}")
        print(f"   Julkaistu: {article.published_at}")
        print(f"   Domain: {article.source_domain}")
        print(f"   Tyyppi: {article.article_type}")
        print(f"   Kieli: {article.language}")
        print(f"   Sisältö (alku): {article.content[:120]}...")
        print(f"   Kontaktit: {article.contacts}")

# Agent flow (before and after):
# feed_reader_agent -> ARTICLE_CONTENT_EXTRACTOR_AGENT (WE ARE HERE) -> news_storer_agent -> news_planner_agent
