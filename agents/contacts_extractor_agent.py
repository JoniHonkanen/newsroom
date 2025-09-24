import logging
from typing import List, Optional

from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.feed_schema import CanonicalArticle
from schemas.parsed_article import NewsContact
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


# LLM-only; heuristisia/HTML-pohjaisia apureita ei käytetä


class ContactsExtractionResult(BaseModel):
    """Structured output wrapper for LLM contact extraction."""

    contacts: List[NewsContact] = Field(default_factory=list)


# LLM prompt for extracting contacts from article content
CONTACTS_EXTRACTION_PROMPT = """
You are a precise information extraction assistant.

Task: Extract contact persons from the following article/press release who are available for media inquiries and follow-up questions.

Look for:
- People listed in "Additional information" / "Media contact" sections
- Contacts provided for follow-up questions
- People quoted in the article who have contact details
- Press/media contacts and spokespersons

For interview purposes, ensure you capture enough identifying information (name + title + organization) so the person can be properly introduced to readers.

Provide for each contact:
- name (if present)
- title (job title/role if present) - important for reader context
- organization (if present) - important for credibility
- email (if present) - recognize various formats like firstname.lastname@company.com, firstname@lastname, etc.
- phone (if present)
- contact_type (spokesperson/expert/decision_maker/general) - infer best guess
- extraction_context (short snippet showing where you found this contact)
- is_primary_contact (mark the designated media contact as true, others false)

Prioritize official media contacts and people explicitly available for questions over those just mentioned in passing.

Article language: {language}

Article content (markdown):
"""


class ContactsExtractorAgent(BaseAgent):
    """Agentti, joka parsii yhteystiedot uutisesta/tiedotteesta.

    LLM-only: poimii yhteystiedot artikkelin markdown-sisällöstä
    strukturoituna ulostulona.
    """

    def __init__(self, llm=None):
        super().__init__(
            llm=llm, prompt=CONTACTS_EXTRACTION_PROMPT, name="ContactsExtractorAgent"
        )

    # HTML-pohjainen fallback poistettu

    def _pick_primary_contact(self, contacts: List[NewsContact]) -> List[NewsContact]:
        if not contacts:
            return contacts
        # Prefer contact with name and email
        best_idx = None
        for i, c in enumerate(contacts):
            if c.name and c.email:
                best_idx = i
                break
        if best_idx is None:
            best_idx = 0
        for i, c in enumerate(contacts):
            c.is_primary_contact = i == best_idx
        return contacts

    def _extract_with_llm(
        self, content_markdown: str, language: str = "fi"
    ) -> List[NewsContact]:
        if not self.llm:
            return []
        try:
            structured_llm = self.llm.with_structured_output(ContactsExtractionResult)
            # Format language placeholder first, then append content to avoid str.format touching user content
            header = self.prompt.format(language=language)
            prompt = f"{header}\n```markdown\n{content_markdown}\n```\n"
            print("TÄMÄ PROMPTI KIINNOSTAAA!!!!")
            print(prompt)
            result = structured_llm.invoke(prompt)
            contacts = list(getattr(result, "contacts", []) or [])
            print("TÄSSÄ KONTAKTIT")
            print(contacts)
            return contacts
        except Exception as e:
            logger.error(f"LLM contact extraction failed: {e}")
            return []

    def run(self, state: AgentState) -> AgentState:
        articles = getattr(state, "articles", [])
        if not articles:
            logger.info("ContactsExtractorAgent: ei artikkeleita käsiteltäväksi.")
            return state

        updated: List[CanonicalArticle] = []
        logger.info(
            f"ContactsExtractorAgent: käsitellään {len(articles)} artikkelia..."
        )

        for art in articles:
            try:
                # Käytä content_extractorilta tullutta markdownia
                article_markdown = getattr(art, "content", None) or ""
                language = getattr(art, "language", "fi") or "fi"
                contacts_llm = self._extract_with_llm(article_markdown, language)
                contacts = self._pick_primary_contact(contacts_llm)

                new_contacts = contacts if contacts else getattr(art, "contacts", [])

                updated.append(
                    art.model_copy(
                        update={
                            "contacts": new_contacts,
                        }
                    )
                )
            except Exception as e:
                logger.error(
                    f"ContactsExtractorAgent: virhe käsiteltäessä artikkelia: {e}"
                )
                updated.append(art)

        state.articles = updated
        logger.info("ContactsExtractorAgent: valmis.")
        return state


if __name__ == "__main__":
    # Savutesti: anna URL, noudetaan markdown parserilla ja poimitaan kontaktit LLM:llä
    import sys
    from dotenv import load_dotenv  # type: ignore
    from services.article_parser import to_structured_article

    load_dotenv()

    url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else input("Anna uutisen/ tiedotteen URL: ").strip()
    )
    if not url:
        print("⚠️  URL puuttuu.")
        sys.exit(1)

    # LLM on pakollinen (LLM-only agentti)
    try:
        from langchain.chat_models import init_chat_model  # lazy import

        llm = init_chat_model("gpt-4o-mini", model_provider="openai")
        print("✅ LLM alustettu (gpt-4o-mini).")
    except Exception as e:
        print(f"❌ LLM ei alustunut: {e}")
        sys.exit(1)

    parsed = to_structured_article(url, check_contact=False)
    if not parsed:
        print("❌ Markdownin nouto epäonnistui.")
        sys.exit(1)

    art = CanonicalArticle(
        title="Test Article",
        link=url,
        unique_id=url,
        content=parsed.markdown,
        published_at=None,
        source_domain=parsed.domain,
        language="fi",
        article_type="press_release",
        contacts=None,
    )

    state = AgentState(articles=[art])
    agent = ContactsExtractorAgent(llm=llm)
    result_state = agent.run(state)

    out = result_state.articles[0]
    contacts = out.contacts or []
    if not contacts:
        print("❌ Yhteystietoja ei löytynyt.")
        sys.exit(0)

    print(f"\n✅ Löytyi {len(contacts)} yhteystietoa:")
    for i, c in enumerate(contacts, 1):
        try:
            data = c.model_dump()
        except Exception:
            data = c.dict() if hasattr(c, "dict") else vars(c)
        print(f"{i}. {data}")
# THIS AGENT EXTRACTS CONTACT INFORMATION FROM THE GIVEN ARTICLE
