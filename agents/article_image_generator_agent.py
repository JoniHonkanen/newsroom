import sys
import os
import requests
import re
import random
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote
from pathlib import Path

# Add the project root to the Python path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle


class ArticleImageGeneratorAgent(BaseAgent):
    """An agent that generates and adds relevant images to enriched articles using Pixabay API."""

    def __init__(
        self, pixabay_api_key: str, image_storage_path: str = "static/images/articles"
    ):
        super().__init__(llm=None, prompt=None, name="ArticleImageGeneratorAgent")
        self.pixabay_api_key = pixabay_api_key
        self.image_storage_path = Path(image_storage_path)
        self.image_storage_path.mkdir(parents=True, exist_ok=True)

    def _search_pixabay_image(
        self, search_term: str, language: str = "en", used_images: set = None
    ) -> Optional[str]:
        """Search for a single relevant image from Pixabay."""
        if used_images is None:
            used_images = set()

        try:
            # Clean and prepare search term
            clean_term = quote(search_term.lower().replace(",", " ").strip())

            # Always use English API since LLM is instructed to provide English search terms
            lang_code = "en"

            # Increase per_page to get more options
            url = f"https://pixabay.com/api/?key={self.pixabay_api_key}&q={clean_term}&safesearch=true&order=popular&image_type=photo&orientation=horizontal&per_page=10&lang={lang_code}"

            print(
                f"           - Searching Pixabay for: '{search_term}' (API language: {lang_code})"
            )

            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("hits") and len(data["hits"]) > 0:
                # Filter out already used images
                available_hits = [
                    hit
                    for hit in data["hits"]
                    if hit["webformatURL"] not in used_images
                ]

                if not available_hits:
                    print(f"           - All images already used for: '{search_term}'")
                    return None

                # Randomly select from first 3 available results
                max_choice = min(3, len(available_hits))
                hit = random.choice(available_hits[:max_choice])

                # Use 340px width for smaller file size
                image_url = hit["webformatURL"].replace("_640", "_340")
                print(f"           - Found image: {image_url}")
                print(
                    f"           - Image tags: {hit.get('tags', 'N/A')}"
                )  # Debug: show image tags
                return image_url
            else:
                print(f"           - No images found for: '{search_term}'")
                return None

        except Exception as e:
            print(f"           - Error searching Pixabay for '{search_term}': {e}")
            return None

    def _extract_image_placeholders(
        self, markdown_content: str
    ) -> List[Tuple[str, str]]:
        """Extract all image placeholders from markdown content.
        Returns list of tuples: (full_match, alt_text)
        """
        pattern = r"!\[([^\]]*)\]\(PLACEHOLDER_IMAGE\)"
        matches = re.findall(pattern, markdown_content)

        placeholders = []
        for match in matches:
            alt_text = match.strip()
            full_match = f"![{alt_text}](PLACEHOLDER_IMAGE)"
            placeholders.append((full_match, alt_text))

        print(f"     - Found {len(placeholders)} image placeholders")
        for i, (_, alt_text) in enumerate(placeholders, 1):
            print(f"       {i}. '{alt_text}'")

        return placeholders

    def _get_search_terms_for_image(
        self,
        alt_text: str,
        article: EnrichedArticle,
        placeholder_index: int,
        used_llm_suggestions: set,
    ) -> Tuple[List[str], str]:
        """Get search terms for an image, prioritizing LLM suggestions.
        Returns (search_terms, primary_llm_suggestion_used)
        """
        search_terms = []
        primary_llm_suggestion = None

        # 1. FIRST PRIORITY: Use LLM's image_suggestions if available
        if hasattr(article, "image_suggestions") and article.image_suggestions:
            print(
                f"           - LLM image suggestions available: {article.image_suggestions}"
            )

            # Try to match placeholder index to suggestion index (if not already used)
            if placeholder_index < len(article.image_suggestions):
                llm_suggestion = article.image_suggestions[placeholder_index]
                if llm_suggestion not in used_llm_suggestions:
                    search_terms.append(llm_suggestion)
                    primary_llm_suggestion = llm_suggestion
                    print(
                        f"           - Using LLM suggestion #{placeholder_index + 1}: '{llm_suggestion}'"
                    )

            # Add other unused LLM suggestions as backup
            for suggestion in article.image_suggestions:
                if (
                    suggestion not in search_terms
                    and suggestion not in used_llm_suggestions
                ):
                    search_terms.append(suggestion)

        # 2. SECOND PRIORITY: Use the alt_text from placeholder
        if alt_text not in search_terms:
            search_terms.append(alt_text)

        # 3. THIRD PRIORITY: Make search term more specific with article context
        specific_term = self._make_search_term_specific(alt_text, article)
        if specific_term not in search_terms:
            search_terms.append(specific_term)

        # 4. LAST RESORT: Category-based fallback terms
        fallback_terms = self._fallback_search_terms(
            article.categories, article.language
        )
        search_terms.extend(fallback_terms)

        return search_terms[:5], primary_llm_suggestion  # Limit to 5 search terms

    def _make_search_term_specific(
        self, alt_text: str, article: EnrichedArticle
    ) -> str:
        """Make search term more specific by combining with article context."""
        # Use article categories or keywords to make search more specific
        context_words = []

        if article.categories:
            context_words.extend(article.categories[:1])  # Take first category

        if article.keywords:
            context_words.extend(article.keywords[:2])  # Take first 2 keywords

        # Combine alt_text with context
        if context_words:
            specific_term = f"{alt_text} {' '.join(context_words[:2])}"
            return specific_term[:50]  # Limit length

        return alt_text

    def _fallback_search_terms(self, categories: List[str], language: str) -> List[str]:
        """Generate fallback search terms based on article categories."""

        # Category to search term mapping
        category_mapping = {
            "politiikka": ["government", "politics", "finland"],
            "politics": ["government", "parliament", "voting"],
            "teknologia": ["technology", "computer", "innovation"],
            "technology": ["technology", "innovation", "digital"],
            "urheilu": ["sports", "athletics", "competition"],
            "sports": ["sports", "athletics", "stadium"],
            "talous": ["business", "economy", "finance"],
            "business": ["business", "economy", "meeting"],
            "terveys": ["health", "medical", "healthcare"],
            "health": ["healthcare", "medical", "hospital"],
            "ympäristö": ["nature", "environment", "green"],
            "environment": ["nature", "environment", "sustainability"],
        }

        fallback_terms = []
        for category in categories[:2]:  # Take first 2 categories
            category_lower = category.lower()
            if category_lower in category_mapping:
                fallback_terms.extend(
                    category_mapping[category_lower][:1]
                )  # Take first term

        # Generic fallback terms
        if not fallback_terms:
            fallback_terms = ["news", "information", "communication"]

        return fallback_terms

    def _download_and_save_image(
        self, image_url: str, article_title: str, image_index: int
    ) -> Optional[str]:
        """Download image from Pixabay and save it locally."""
        try:
            # Create unique filename from article title
            from datetime import datetime

            # Clean title (first 20 chars, safe for filename)
            clean_title = article_title[:20].lower()
            clean_title = re.sub(
                r"[^a-z0-9\s]", "", clean_title
            )  # Remove special chars
            clean_title = re.sub(
                r"\s+", "_", clean_title.strip()
            )  # Replace spaces with underscore

            # Add date and image index
            date_str = datetime.now().strftime("%Y%m%d")
            filename = f"{clean_title}_{image_index}_{date_str}.jpg"
            local_path = self.image_storage_path / filename

            print(f"           - Downloading image to: {local_path}")

            # Download image
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()

            # Save image
            with open(local_path, "wb") as f:
                f.write(response.content)

            # Return relative URL for web usage
            web_url = f"/static/images/articles/{filename}"
            print(f"           - Saved as: {web_url}")

            return web_url

        except Exception as e:
            print(f"           - Error downloading image: {e}")
            return None

    def _process_article_images(self, article: EnrichedArticle) -> EnrichedArticle:
        """Process all images in an enriched article."""

        print(f"     - Processing images for: {article.enriched_title[:60]}...")

        # Extract all image placeholders
        placeholders = self._extract_image_placeholders(article.enriched_content)

        if not placeholders:
            print(f"     - No image placeholders found in article")
            return article

        # Show LLM suggestions if available
        if hasattr(article, "image_suggestions") and article.image_suggestions:
            print(
                f"     - LLM provided {len(article.image_suggestions)} image suggestions: {article.image_suggestions}"
            )
        else:
            print(f"     - No LLM image suggestions available, using fallback methods")

        # Process each placeholder
        updated_content = article.enriched_content
        hero_image_url = None
        successful_replacements = 0
        used_images = set()  # Track used images to avoid duplicates
        used_llm_suggestions = set()  # Track used LLM suggestions to avoid duplicates

        for i, (full_match, alt_text) in enumerate(placeholders):
            print(f"     - Processing image {i+1}/{len(placeholders)}: '{alt_text}'")

            # Get prioritized search terms for this image
            search_terms, primary_llm_suggestion = self._get_search_terms_for_image(
                alt_text, article, i, used_llm_suggestions
            )
            print(f"           - Search terms: {search_terms}")

            image_url = None
            used_search_term = None

            # Try each search term until we find an image
            for search_term in search_terms:
                print(f"           - Trying search term: '{search_term}'")
                image_url = self._search_pixabay_image(
                    search_term, article.language, used_images
                )
                if image_url:
                    used_search_term = search_term
                    break

            # Only mark LLM suggestion as used if it was actually used for the image
            if (
                image_url
                and used_search_term
                and primary_llm_suggestion
                and used_search_term == primary_llm_suggestion
            ):
                used_llm_suggestions.add(primary_llm_suggestion)
                print(
                    f"           - Marked LLM suggestion '{primary_llm_suggestion}' as used"
                )

            if image_url:
                # Add to used images set
                used_images.add(image_url)

                # Download image locally
                local_url = self._download_and_save_image(
                    image_url, article.enriched_title, i + 1
                )

                if local_url:
                    # Handle hero image (first placeholder) separately
                    if hero_image_url is None:
                        hero_image_url = local_url
                        # Remove the placeholder from the content instead of replacing it
                        updated_content = updated_content.replace(
                            full_match, ""
                        ).strip()
                        print(f"           - Set as hero image: {local_url}")
                        print(f"           - Removed hero placeholder from content")
                    else:
                        # For other images, replace the placeholder in the content
                        replacement = f"![{alt_text}]({local_url})"
                        updated_content = updated_content.replace(
                            full_match, replacement
                        )
                        print(f"           - Replaced placeholder in content")

                    successful_replacements += 1
                else:
                    # Remove placeholder if download failed
                    updated_content = updated_content.replace(full_match, "")
                    print(f"           - Removed placeholder {i+1} (download failed)")
            else:
                # Remove placeholder if no image found
                updated_content = updated_content.replace(full_match, "")
                print(f"           - Removed placeholder {i+1} (no image found)")

        print(
            f"     - Successfully processed {successful_replacements}/{len(placeholders)} images"
        )

        # CRITICAL: Ensure ALL remaining PLACEHOLDER_IMAGE references are removed
        remaining_placeholders = updated_content.count("PLACEHOLDER_IMAGE")
        if remaining_placeholders > 0:
            print(
                f"     - WARNING: Found {remaining_placeholders} remaining placeholders, removing them..."
            )
            # Remove any remaining placeholder patterns
            updated_content = re.sub(
                r"!\[[^\]]*\]\(PLACEHOLDER_IMAGE\)", "", updated_content
            )
            print(f"     - Cleaned all remaining PLACEHOLDER_IMAGE references")

        # Create updated article
        article_data = article.model_dump()
        article_data.update(
            {"enriched_content": updated_content, "hero_image_url": hero_image_url}
        )
        enhanced_article = EnrichedArticle(**article_data)

        return enhanced_article

    def run(self, state: AgentState) -> AgentState:
        """Add relevant images to enriched articles."""

        print("ArticleImageGeneratorAgent: Starting to generate images for articles...")

        if not state.enriched_articles:
            print("ArticleImageGeneratorAgent: No enriched articles to process.")
            return state

        if not self.pixabay_api_key:
            print(
                "ArticleImageGeneratorAgent: No Pixabay API key provided. Skipping image generation."
            )
            return state

        print(
            f"ArticleImageGeneratorAgent: Processing {len(state.enriched_articles)} articles..."
        )

        enhanced_articles = []

        for i, article in enumerate(state.enriched_articles, 1):
            print(f"\n   - Processing article {i}/{len(state.enriched_articles)}")
            try:
                enhanced_article = self._process_article_images(article)
                enhanced_articles.append(enhanced_article)

            except Exception as e:
                print(f"     - Error processing article images: {e}")
                # Keep original article if image processing fails
                enhanced_articles.append(article)

        state.enriched_articles = enhanced_articles
        print(
            f"\nArticleImageGeneratorAgent: Completed image processing for {len(enhanced_articles)} articles"
        )

        return state


if __name__ == "__main__":
    from dotenv import load_dotenv
    from schemas.enriched_article import EnrichedArticle
    from schemas.agent_state import AgentState

    print("--- Testing ArticleImageGeneratorAgent in isolation ---")
    load_dotenv()

    # Get Pixabay API key from environment
    pixabay_key = os.getenv("PIXABAY_API_KEY")
    if not pixabay_key:
        print("❌ PIXABAY_API_KEY not found in environment variables")
        exit(1)

    # Create test enriched article with image placeholders AND LLM suggestions
    test_article = EnrichedArticle(
        article_id="test-image-article",
        canonical_news_id=123,
        enriched_title="Finland's AI Strategy Test Article",
        enriched_content="""![main topic](PLACEHOLDER_IMAGE)

Finland has made significant investments in AI technology development.

![ai research](PLACEHOLDER_IMAGE)

The country plans to establish research centers across multiple cities.

### Future Developments

More developments are expected in the coming months.

![government building](PLACEHOLDER_IMAGE)

This initiative represents Finland's commitment to technological advancement.""",
        published_at="2024-08-06",
        source_domain="test.com",
        keywords=["Finland", "AI", "technology"],
        categories=["Technology", "Politics"],
        language="en",
        sources=["http://test.com"],
        references=[],
        locations=[],
        summary="Finland invests in AI technology development",
        enrichment_status="success",
        hero_image_url=None,  # Should be set by the agent
        image_suggestions=[
            "finnish parliament",
            "ai laboratory",
            "technology center",
        ],  # LLM suggestions
    )

    # Create test state
    test_state = AgentState(
        articles=[],
        plan=[],
        article_search_map={},
        canonical_ids={},
        enriched_articles=[test_article],
    )

    print(f"\nTest setup:")
    print(f"- Input articles: {len(test_state.enriched_articles)}")
    print(f"- Pixabay API key: {'✓' if pixabay_key else '✗'}")
    print(f"- LLM image suggestions: {test_article.image_suggestions}")

    # Create and run the agent
    image_agent = ArticleImageGeneratorAgent(pixabay_key)

    print("\n--- Running ArticleImageGeneratorAgent ---")
    result_state = image_agent.run(test_state)
    print("--- Agent completed ---")

    # Print results
    print("\n--- Results ---")
    if result_state.enriched_articles:
        for i, article in enumerate(result_state.enriched_articles):
            print(f"\n=== ARTICLE {i+1} RESULTS ===")
            print(f"Title: {article.enriched_title}")
            print(f"Hero Image URL: {article.hero_image_url}")
            print(f"Categories: {article.categories}")
            print(f"LLM Suggestions: {getattr(article, 'image_suggestions', 'None')}")

            # Count images in content
            image_count = article.enriched_content.count("![")
            placeholder_count = article.enriched_content.count("PLACEHOLDER_IMAGE")

            print(f"Images in content: {image_count}")
            print(f"Remaining placeholders: {placeholder_count}")

            print(f"\n--- UPDATED CONTENT ---")
            print(article.enriched_content)
            print(f"--- END CONTENT ---")
    else:
        print("No articles processed")
