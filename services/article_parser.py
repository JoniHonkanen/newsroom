# services/article_parser.py - HTML -> Markdown parser (contacts handled elsewhere)

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import trafilatura
from schemas.parsed_article import ParsedArticle

# --- Logging-konfiguraatio ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- PÄÄFUNKTIO ---


def to_structured_article(url: str, check_contact: bool = False) -> Optional[ParsedArticle]:
    """NOPEA artikkelin käsittely BeautifulSoup:lla."""
    logging.info(f"🚀 Käsitellään artikkeli: {url}")

    # 1. Nouda HTML
    downloaded_html = trafilatura.fetch_url(url)
    if not downloaded_html:
        logging.error(f"❌ Artikkelin nouto epäonnistui: {url}")
        return None

    # 2. Trafilatura-käsittely
    main_content_text = trafilatura.extract(downloaded_html)
    metadata = trafilatura.extract_metadata(downloaded_html)

    if not main_content_text and not metadata:
        logging.error(f"❌ Trafilatura ei löytänyt sisältöä: {url}")
        return None

    # 3. Luo Markdown
    final_markdown = ""
    if metadata and metadata.title:
        final_markdown = f"# {metadata.title}\n\n"
    if main_content_text:
        # Escapeta Markdown-merkit
        cleaned_text = main_content_text.replace("*", "\\*").replace("_", "\\_")
        final_markdown += cleaned_text.strip()

    # 4. Yhteystietojen haku poistettu tästä modulista.
    #    Kontaktien poiminnan hoitaa ContactsExtractorAgent myöhemmässä vaiheessa.
    if check_contact:
        logging.info("ℹ️ Yhteystietojen haku on siirretty ContactsExtractorAgentiin. Ohitetaan.")

    # 5. Julkaisupäivä
    published_dt = None
    if metadata and metadata.date:
        try:
            published_dt = datetime.fromisoformat(metadata.date.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            logging.warning(f"⚠️ Päivämäärän käsittely epäonnistui: {metadata.date}")

    return ParsedArticle(
        domain=urlparse(url).netloc.replace("www.", ""),
        published=published_dt,
        markdown=final_markdown.strip(),
        contacts=[],
    )
