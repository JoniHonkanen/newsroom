from typing import Any, List
from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.feed_schema import CanonicalArticle
from schemas.parsed_article import NewsContact  # Lisätty kontaktien tallennusta varten
import psycopg  # type: ignore
import hashlib
from sentence_transformers import SentenceTransformer  # type: ignore
import datetime

try:
    from dateutil import parser as date_parser
except ImportError:
    date_parser = None


class NewsStorerAgent(BaseAgent):
    """Agent that stores news articles into PostgreSQL with hash- and embedding-based dedupe (pre-check),
    allowing re-insertion if semantically similar article is older than a time threshold.
    Now also stores contact information if available.
    """

    def __init__(self, db_dsn: str, threshold: float = 0.1, time_window_days: int = 2):
        super().__init__(llm=None, prompt=None, name="NewsStorerAgent")
        self.db_dsn = db_dsn
        # we need to detect multilingual articles, so we use a multilingual model
        self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        self.threshold = threshold
        self.time_window = datetime.timedelta(days=time_window_days)

    def _normalize(self, text: str) -> str:
        """Normalize text by stripping whitespace and removing extra spaces."""
        return " ".join(text.split())

    def _calc_hash(self, text: str) -> str:
        """Calculate SHA-256 hash of the normalized text."""
        h = hashlib.sha256()
        h.update(text.encode("utf-8"))
        return h.hexdigest()

    def _encode(self, text: str) -> list[float]:
        """Encode text into a vector using the SentenceTransformer model."""
        return (
            self.model.encode(text, normalize_embeddings=True)
            .astype("float32")
            .tolist()
        )

    def _parse_published(self, published: Any) -> datetime.datetime:
        """Ensure published_at is a naive datetime object (UTC)."""
        if isinstance(published, datetime.datetime):
            dt = published
        elif isinstance(published, str):
            try:
                if date_parser:
                    dt = date_parser.parse(published)
                else:
                    dt = datetime.datetime.fromisoformat(
                        published.replace("Z", "+00:00")
                    )
            except Exception:
                raise ValueError(f"Unable to parse published timestamp: {published}")
        else:
            raise TypeError(f"Unsupported type for published: {type(published)}")
        # Ensure timezone is UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        else:
            dt = dt.astimezone(datetime.timezone.utc)
        return dt

    def _store_contacts(
        self, conn, canonical_id: int, contacts: List[NewsContact]
    ) -> None:
        """Store contact information for a canonical news article."""
        if not contacts:
            return

        print(f"Storing {len(contacts)} contacts for canonical_id={canonical_id}")

        for contact in contacts:
            try:
                conn.execute(
                    """
                    INSERT INTO news_contacts
                        (canonical_news_id, name, title, organization, phone, email, 
                         contact_type, extraction_context, is_primary_contact, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        canonical_id,
                        contact.name,
                        contact.title,
                        contact.organization,
                        contact.phone,
                        contact.email,
                        contact.contact_type or "spokesperson",
                        contact.extraction_context,
                        contact.is_primary_contact or False,
                        datetime.datetime.now(datetime.timezone.utc),
                        datetime.datetime.now(datetime.timezone.utc),
                    ),
                )
                print(
                    f"  → Stored contact: {contact.name or 'Unknown'} ({contact.email})"
                )
            except Exception as e:
                print(
                    f"  ⚠️ Failed to store contact {contact.name or contact.email}: {e}"
                )

    def run(self, state: AgentState) -> AgentState:
        articles = state.articles
        if not articles:
            print("NewsStorerAgent: No new articles.")
            return state

        processed_articles: List[CanonicalArticle] = []  # Tyypitetty lista

        with psycopg.connect(self.db_dsn) as conn:
            with conn.transaction():
                for art in articles:
                    raw = art.content or ""
                    # skip empty articles
                    if not raw.strip():
                        print(f"Skipping article with empty content: url={art.link}")
                        continue
                    print(f"Processing raw article: {raw[:100]}...")
                    norm = self._normalize(raw)
                    print(
                        f"Normalized content: {norm[:100]}..."
                    )  # Print first 100 chars for brevity
                    h = self._calc_hash(norm)  # hashing

                    # Korjattu: käytä published_at ensisijaisesti
                    published_dt = self._parse_published(art.published_at)

                    # 1. Hash-duplication
                    row = conn.execute(
                        "SELECT id FROM canonical_news WHERE content_hash = %s",
                        (h,),
                    ).fetchone()
                    if row:
                        print(
                            f"Skipping by hash duplicate: canonical_id={row[0]}, url={art.link}"
                        )
                        continue  # Skip tämä artikkeli - ei lisätä processed_articles:iin

                    # 2. Embedding pre-check - rajoita aikaikkunaan
                    emb = self._encode(norm)
                    time_threshold = published_dt - self.time_window
                    sim = conn.execute(
                        """
                        SELECT id, published_at, content_embedding <=> %s::vector AS dist
                        FROM canonical_news
                        WHERE published_at >= %s
                        ORDER BY dist
                        LIMIT 1
                        """,
                        (emb, time_threshold),
                    ).fetchone()

                    if sim:
                        similar_id, sim_published, dist = sim
                        if (
                            isinstance(sim_published, str)
                            or sim_published.tzinfo is not None
                        ):
                            sim_published = self._parse_published(sim_published)
                        if dist < self.threshold:
                            print(
                                f"Found semantic duplicate: canonical_id={similar_id}, dist={dist:.4f}, url={art.link}"
                            )
                            # Insert it into news_sources if not already linked, so on conflict we do nothing
                            result = conn.execute(
                                """
                                INSERT INTO news_sources
                                    (canonical_news_id, source_name, source_url, original_guid, published_at, article_type)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (source_url) DO NOTHING
                                """,
                                (
                                    similar_id,
                                    art.source_domain,  # Poistettu getattr
                                    art.link,
                                    art.unique_id,  # Poistettu getattr
                                    published_dt,
                                    art.article_type,
                                ),
                            )
                            if result.rowcount:
                                print(
                                    f"  → Linked new source for canonical_id={similar_id}"
                                )
                            else:
                                print(
                                    f"  → Source already linked for canonical_id={similar_id}"
                                )

                            if hasattr(art, "contacts") and art.contacts:
                                # Tarkista onko canonical artikkelilla jo kontakteja
                                existing_contacts = conn.execute(
                                    "SELECT COUNT(*) FROM news_contacts WHERE canonical_news_id = %s",
                                    (similar_id,),
                                ).fetchone()[0]

                                if existing_contacts == 0:
                                    print(
                                        f"  → Adding contacts to existing canonical_id={similar_id}"
                                    )
                                    self._store_contacts(conn, similar_id, art.contacts)
                                else:
                                    print(
                                        f"  → Canonical article already has {existing_contacts} contacts, skipping"
                                    )

                            continue

                    # 3. add new article
                    row = conn.execute(
                        """
                        INSERT INTO canonical_news
                            (title,
                             content,
                             published_at,
                             created_at,
                             content_hash,
                             content_embedding,
                             source_name,
                             source_url,
                             language,
                             article_type)
                        VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            art.title,
                            norm,
                            published_dt,
                            datetime.datetime.now(datetime.timezone.utc),
                            h,
                            emb,
                            art.source_domain,  # Poistettu getattr
                            art.link,
                            art.language,
                            art.article_type,
                        ),
                    ).fetchone()
                    canonical_id = row[0]
                    print(
                        f"Inserted new canonical_news id={canonical_id}, url={art.link}"
                    )

                    # LISÄTTY: Tallenna kontaktit uudelle artikkelille
                    if hasattr(art, "contacts") and art.contacts:
                        self._store_contacts(conn, canonical_id, art.contacts)

                    # Store article_id -> canonical_id mapping in state
                    if not hasattr(state, "canonical_ids"):
                        # TODO:: MIELESTÄNI TÄÄ VOI OLLA VÄHÄN TURHA... KATO JOS POISTETTAIS!!!
                        state.canonical_ids = {}
                    state.canonical_ids[art.unique_id or art.link] = canonical_id

                    # Lisää vain todella tallennetut artikkelit
                    processed_articles.append(art)

        # Päivitä state.articles sisältämään vain uudet, tallennetut artikkelit
        state.articles = processed_articles

        if processed_articles:
            print(f"NewsStorerAgent: Stored {len(processed_articles)} new articles.")
        else:
            print("NewsStorerAgent: No new articles to store - all were duplicates.")

        return state
