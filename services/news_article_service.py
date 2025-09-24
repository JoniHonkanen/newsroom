# File: services/news_article_service.py

import sys
import os
import re
import markdown
from datetime import datetime
from typing import List, Dict, Any, Optional
import psycopg  # type: ignore
from psycopg.types.json import Jsonb  # type: ignore
import numpy as np

# Add project root to path for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schemas.enriched_article import EnrichedArticle, ArticleReference, LocationTag
from schemas.news_article_db import NewsArticleDB


class NewsArticleService:
    """Service for managing news articles in the database."""

    def __init__(self, db_dsn: str):
        """Initialize with database connection string."""
        self.db_dsn = db_dsn
        self._setup_tables()

    def _setup_tables(self):
        """
        Make sure the database is ready. Tables should be created by the enable_pgvector.sql script
        when the container starts, but we'll add indexes if they don't exist.
        """
        with psycopg.connect(self.db_dsn) as conn:
            with conn.cursor() as cur:
                # Create helpful indexes if they don't exist
                cur.execute(
                    """
                CREATE INDEX IF NOT EXISTS idx_news_article_canonical_id ON news_article(canonical_news_id);
                CREATE INDEX IF NOT EXISTS idx_news_article_language ON news_article(language);
                CREATE INDEX IF NOT EXISTS idx_news_article_status ON news_article(status);                """
                )
                conn.commit()

    def _convert_markdown_to_html_blocks(
        self, markdown_text: str
    ) -> List[Dict[str, Any]]:
        """
        Convert markdown text to a list of HTML content blocks.
        Each block will be a dictionary with type, content and potentially other attributes.
        Preserves the original order of elements in the document.
        """
        # Convert the full markdown to HTML
        html = markdown.markdown(markdown_text, extensions=["tables", "fenced_code"])

        # Keep track of processed content to avoid duplicates
        processed_ranges = []

        # Define patterns to match different HTML elements
        block_patterns = [
            # Headers
            (
                r"<h([1-6])>(.*?)</h\1>",
                lambda m: {
                    "type": f"h{m.group(1)}",
                    "content": m.group(2),
                    "html": m.group(0),
                },
            ),
            # Images (process FIRST to avoid duplicates in paragraphs)
            (
                r"<img\s+([^>]+)>",
                lambda m: {
                    "type": "image",
                    "content": m.group(0),
                    "html": m.group(0),
                    # Extract src and alt if available
                    "src": (
                        re.search(r'src="([^"]+)"', m.group(1)).group(1)
                        if re.search(r'src="([^"]+)"', m.group(1))
                        else ""
                    ),
                    "alt": (
                        re.search(r'alt="([^"]+)"', m.group(1)).group(1)
                        if re.search(r'alt="([^"]+)"', m.group(1))
                        else ""
                    ),
                },
            ),
            # Code blocks
            (
                r"<pre><code>(.*?)</code></pre>",
                lambda m: {
                    "type": "code",
                    "content": m.group(1),
                    "html": m.group(0),
                },
            ),
            # Blockquotes
            (
                r"<blockquote>(.*?)</blockquote>",
                lambda m: {
                    "type": "quote",
                    "content": m.group(1),
                    "html": m.group(0),
                },
            ),
            # Lists
            (
                r"<(ul|ol)>(.*?)</\1>",
                lambda m: {
                    "type": "list",
                    "content": m.group(2),
                    "html": m.group(0),
                },
            ),
            # Paragraphs (process LAST to avoid including already processed images)
            (
                r"<p>(.*?)</p>",
                lambda m: {
                    "type": "text",
                    "content": m.group(1),
                    "html": m.group(0),
                },
            ),
        ]

        # Find all HTML elements and their positions
        all_matches = []

        for pattern, block_handler in block_patterns:
            for match in re.finditer(pattern, html, re.DOTALL):
                start, end = match.span()

                # Check if this range overlaps with already processed content
                overlaps = any(
                    start < proc_end and end > proc_start
                    for proc_start, proc_end in processed_ranges
                )

                if not overlaps:
                    block_data = block_handler(match)

                    # Special handling for paragraphs: remove any img tags that were already processed
                    if block_data["type"] == "text":
                        # Remove img tags from paragraph content
                        clean_content = re.sub(
                            r"<img\s+[^>]+>", "", block_data["content"]
                        ).strip()
                        clean_html = f"<p>{clean_content}</p>" if clean_content else ""

                        # Skip empty paragraphs
                        if not clean_content:
                            continue

                        block_data["content"] = clean_content
                        block_data["html"] = clean_html

                    all_matches.append((start, end, block_data))
                    processed_ranges.append((start, end))

        # Sort matches by their position in the document
        all_matches.sort(key=lambda x: x[0])

        # Create the ordered list of blocks
        blocks = []
        for i, (_, _, block_data) in enumerate(all_matches, 1):
            # Skip empty quote blocks
            if block_data["type"] == "quote" and not block_data["content"].strip():
                continue

            # Skip empty text blocks
            if block_data["type"] == "text" and not block_data["content"].strip():
                continue

            block_data["order"] = i
            blocks.append(block_data)

        return blocks

    def _convert_location_tags(
        self, location_tags: Optional[List[LocationTag]]
    ) -> Optional[Dict[str, Any]]:
        """Convert LocationTag objects to JSON structure for database storage."""
        if not location_tags:
            return None

        # Convert list of LocationTag objects to a dictionary with locations as a list
        return {"locations": [tag.dict(exclude_none=True) for tag in location_tags]}

    def _convert_article_references(
        self, references: Optional[List[ArticleReference]]
    ) -> Optional[List[Dict[str, str]]]:
        """Convert ArticleReference objects to JSON structure for database storage."""
        if not references:
            return (
                []
            )  # Palauta tyhjä lista None:n sijaan, jotta JSONilla on aina jokin arvo

        # Varmistetaan, että kaikki tarvittavat kentät ovat mukana
        return [
            {
                "title": (
                    ref.title
                    if hasattr(ref, "title")
                    else (
                        f"Source from {ref.source}"
                        if hasattr(ref, "source")
                        else "Unknown source"
                    )
                ),
                "url": ref.url if hasattr(ref, "url") else "",
                "source": ref.source if hasattr(ref, "source") else "",
            }
            for ref in references
        ]

    def _ensure_canonical_news_exists(self, article_url: str) -> int:
        """
        Ensure that the canonical_news record exists for the given article URL.
        If the URL looks like an integer, use it as the ID.
        Otherwise, look up or create a canonical_news entry for the URL.
        """
        try:
            # Try to parse as integer directly
            return int(article_url)
        except ValueError:
            # If it's not an integer, it's probably a URL
            # Check if we already have this URL in canonical_news
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    # Try to find an existing entry by source_url
                    cur.execute(
                        "SELECT id FROM canonical_news WHERE source_url = %s",
                        (article_url,),
                    )
                    result = cur.fetchone()

                    if result:
                        # Return existing ID if found
                        return result[0]
                    else:
                        # Create a new entry in canonical_news
                        cur.execute(
                            """
                            INSERT INTO canonical_news 
                            (title, content, source_url, created_at) 
                            VALUES (%s, %s, %s, NOW())
                            RETURNING id
                            """,
                            (
                                f"Article from {article_url}",  # Placeholder title
                                "",  # Empty content
                                article_url,
                            ),
                        )
                        new_id = cur.fetchone()[0]
                        conn.commit()
                        return new_id

    def save_enriched_article(self, article: EnrichedArticle) -> int:
        """
        Save an enriched article to the database.
        Returns the ID of the created database record.
        """
        # Extract the lead paragraph (first sentence or paragraph)
        content_parts = article.enriched_content.split("\n\n", 1)
        lead = content_parts[0].strip()

        # Convert markdown to HTML blocks
        body_blocks = self._convert_markdown_to_html_blocks(article.enriched_content)

        # Convert location tags and references to JSON
        location_tags_json = self._convert_location_tags(article.locations)
        sources_json = self._convert_article_references(article.references)
        enrichment_status = getattr(article, "enrichment_status", "pending")

        # we also want to add categories to the news_article table (added 6.8.2025), so its easier to show in frontend
        categories_array = [category.lower() for category in article.categories]

        db_article = NewsArticleDB(
            canonical_news_id=(
                article.canonical_news_id
                if article.canonical_news_id
                else self._ensure_canonical_news_exists(article.article_id)
            ),  # Use provided canonical ID or look it up
            language=article.language,
            version=1,  # Initial version
            lead=lead,
            summary=getattr(article, "summary", article.enriched_content[:300] + "..."),
            status="draft",  # Default status
            location_tags=location_tags_json,
            sources=sources_json,
            interviews=None,  # Not implemented yet
            review_status="standard",  # Default status for editorial review
            author="AI Assistant",  # Default author
            embedding=None,
            body_blocks=body_blocks,
            markdown_content=article.enriched_content,  # Tallennetaan alkuperäinen markdown
            published_at=None,
            updated_at=datetime.now(),
            enrichment_status=enrichment_status,
            original_article_type=article.original_article_type,
            hero_image_url=article.hero_image_url,
        )  # Save to database
        with psycopg.connect(self.db_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                INSERT INTO news_article 
                (canonical_news_id, language, version, lead, summary, status, 
                 location_tags, sources, interviews, review_status, author, 
                 embedding, body_blocks, markdown_content, published_at, updated_at,
                 enrichment_status, original_article_type,
                 required_corrections, revision_count, categories, hero_image_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                    (
                        db_article.canonical_news_id,
                        db_article.language,
                        db_article.version,
                        db_article.lead,
                        db_article.summary,
                        db_article.status,
                        (
                            Jsonb(db_article.location_tags)
                            if db_article.location_tags
                            else None
                        ),
                        Jsonb(db_article.sources) if db_article.sources else None,
                        Jsonb(db_article.interviews) if db_article.interviews else None,
                        db_article.review_status,
                        db_article.author,
                        None,  # embedding -> This will be None for now, set when published
                        Jsonb(db_article.body_blocks),
                        db_article.markdown_content,  # Tallennetaan alkuperäinen markdown
                        None,  # No published_at yet, will be set later
                        db_article.updated_at,
                        db_article.enrichment_status,
                        db_article.original_article_type,
                        False,  # required_corrections
                        0,  # revision_count
                        categories_array,
                        db_article.hero_image_url,
                    ),
                )

                article_id = cur.fetchone()[0]

                # Save categories
                for category in article.categories:
                    # First, ensure the category exists
                    cur.execute(
                        "INSERT INTO category (slug) VALUES (%s) ON CONFLICT (slug) DO NOTHING",
                        (category.lower(),),
                    )
                    # Get the category ID
                    cur.execute(
                        "SELECT id FROM category WHERE slug = %s", (category.lower(),)
                    )
                    category_id = cur.fetchone()[0]
                    # Link article to category
                    cur.execute(
                        "INSERT INTO news_article_category (category_id, article_id) VALUES (%s, %s)",
                        (category_id, article_id),
                    )

                # Save keywords
                for keyword in article.keywords:
                    # First, ensure the keyword exists
                    cur.execute(
                        "INSERT INTO keyword (slug) VALUES (%s) ON CONFLICT (slug) DO NOTHING",
                        (keyword.lower(),),
                    )
                    # Get the keyword ID
                    cur.execute(
                        "SELECT id FROM keyword WHERE slug = %s", (keyword.lower(),)
                    )
                    keyword_id = cur.fetchone()[0]
                    # Link article to keyword
                    cur.execute(
                        "INSERT INTO news_article_keyword (keyword_id, article_id) VALUES (%s, %s)",
                        (keyword_id, article_id),
                    )

                conn.commit()

                return article_id

    # This is used to update article, that has been fixed by article_fixer_agent
    def update_enriched_article(self, article: EnrichedArticle) -> None:
        """
        Update an existing enriched article in the database.
        """
        if not article.news_article_id:
            print("❌ Cannot update: article has no database ID")
            return False

        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    # Päivitä markdown ja body blocks
                    body_blocks = self._convert_markdown_to_html_blocks(
                        article.enriched_content
                    )

                    cur.execute(
                        """
                        UPDATE news_article 
                        SET markdown_content = %s,
                            body_blocks = %s,
                            lead = %s,
                            summary = %s,
                            required_corrections = %s,
                            revision_count = %s,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (
                            article.enriched_content,
                            Jsonb(body_blocks),
                            article.enriched_content.split("\n\n", 1)[0].strip(),
                            article.summary,
                            True,
                            article.revision_count,
                            article.news_article_id,
                        ),
                    )

                    conn.commit()
                    print(
                        f"✅ Updated article {article.news_article_id} after corrections"
                    )
                    return True

        except Exception as e:
            print(f"❌ Error updating article: {e}")
            return False

    def update_article_after_interview(
        self,
        news_article_id: int,
        markdown_content: str,
        summary: Optional[str] = None,
        revision_increment: int = 1,
    ) -> bool:
        """
        Update an article after interview enrichment.

        - Recomputes body_blocks from markdown
        - Updates lead (first paragraph), summary, markdown_content
        - Increments revision_count
        - Clears required_corrections (False)
        """
        try:
            # Convert markdown to body blocks and derive lead
            blocks = self._convert_markdown_to_html_blocks(markdown_content)
            lead = markdown_content.split("\n\n", 1)[0].strip() if markdown_content else None
            summary_val = summary or (markdown_content[:300] + "...")

            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE news_article
                        SET markdown_content = %s,
                            body_blocks = %s,
                            lead = %s,
                            summary = %s,
                            required_corrections = FALSE,
                            revision_count = COALESCE(revision_count, 0) + %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            markdown_content,
                            Jsonb(blocks),
                            lead,
                            summary_val,
                            revision_increment,
                            news_article_id,
                        ),
                    )
                    conn.commit()
                    print(f"✅ Updated article {news_article_id} after interview enrichment")
                    return True
        except Exception as e:
            print(f"❌ Error updating article after interview: {e}")
            return False
