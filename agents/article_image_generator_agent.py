import sys
import os
import requests
import re
import random
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote
from pathlib import Path

# Add the project root to the Python path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle

try:
    from runware import Runware, IImageInference
    RUNWARE_AVAILABLE = True
except ImportError:
    RUNWARE_AVAILABLE = False
    print("⚠️  Warning: Runware SDK not available. Will use Pixabay only.")


class ArticleImageGeneratorAgent(BaseAgent):
    """An agent that generates and adds relevant images to enriched articles.
    
    Uses AI image generation (Runware) as primary method and Pixabay API as fallback.
    """

    def __init__(
        self,
        pixabay_api_key: str,
        runware_api_key: Optional[str] = None,
        image_storage_path: str = "static/images/articles",
        use_ai_generation: bool = True,
    ):
        super().__init__(llm=None, prompt=None, name="ArticleImageGeneratorAgent")
        
        self.logger = logging.getLogger(__name__)
        
        self.pixabay_api_key = pixabay_api_key
        self.runware_api_key = runware_api_key or os.getenv("RUNWARE_API_KEY")
        self.use_ai_generation = use_ai_generation and RUNWARE_AVAILABLE
        
        self.image_storage_path = Path(image_storage_path)
        self.image_storage_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize Runware if available
        self.runware = None
        if self.use_ai_generation and self.runware_api_key:
            self.runware = Runware(api_key=self.runware_api_key)
            print("✅ Runware AI image generation enabled")
        elif self.use_ai_generation:
            print("⚠️  Warning: RUNWARE_API_KEY not provided, falling back to Pixabay only")
            self.use_ai_generation = False

    async def _generate_ai_image(self, prompt: str, negative_prompt: Optional[str] = None) -> Optional[str]:
        """Generate an image using Runware AI - returns image URL directly"""
        if not self.runware:
            return None
            
        try:
            # Connect to Runware if not connected
            if not hasattr(self, '_runware_connected'):
                await self.runware.connect()
                self._runware_connected = True
            
            # Prepare image generation request
            request = IImageInference(
                positivePrompt=prompt,
                negativePrompt=negative_prompt or "blurry, low quality, distorted, watermark, text",
                width=1024,  # Mobile portrait: 9:16 aspect ratio
                height=576,  # Taller than wide for mobile
                model="runware:100@1",  # CHEAP MODEL
                steps=5,  # Good balance between quality and speed
                CFGScale=7,  # High prompt adherence
                numberResults=1,
                outputType="URL",  # Get URL directly
                outputFormat="WEBP",  # Better compression than JPG
                outputQuality=85,  # Good quality without max size
                scheduler="DPM++ 2M Karras",  # Efficient scheduler for good quality
            )
            
            # Generate image
            images = await self.runware.imageInference(requestImage=request)
            
            if images and len(images) > 0:
                image_url = images[0].imageURL
                self.logger.info(f"✅ AI generated image: {image_url}")
                return image_url
            else:
                self.logger.error("❌ No images returned from AI generation")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Failed to generate AI image: {e}")
            return None

    def _search_pixabay_image(
        self, search_term: str, language: str = "en", used_images: set = None
    ) -> Optional[str]:
        """Search for a single relevant image from Pixabay (fallback method)."""
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
        e.g., [('![main topic](PLACEHOLDER_IMAGE)', 'main topic'), ...]
        """
        # Match markdown image placeholders: ![alt text](PLACEHOLDER_IMAGE)
        pattern = r"!\[([^\]]*)\]\(PLACEHOLDER_IMAGE\)"
        matches = re.findall(pattern, markdown_content)

        # Return both full match and alt text
        full_matches = re.finditer(pattern, markdown_content)
        return [(match.group(0), match.group(1)) for match in full_matches]

    def _get_fallback_search_terms(self, categories: List[str]) -> List[str]:
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
        """Download image from URL and save it locally."""
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
            
            # Determine file extension from URL
            extension = "jpg"
            if ".webp" in image_url.lower():
                extension = "webp"
            elif ".png" in image_url.lower():
                extension = "png"
                
            filename = f"{clean_title}_{image_index}_{date_str}.{extension}"
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

    async def _get_image_for_search_term_async(
        self, search_term: str, used_images: set, article_language: str = "en"
    ) -> Optional[str]:
        """Get image for a search term - tries AI generation first, then Pixabay fallback"""
        
        # Try AI generation first if enabled
        if self.use_ai_generation and self.runware:
            print(f"           - Trying AI generation for: '{search_term}'")
            
            # Enhance prompt for better results
            enhanced_prompt = f"professional news photography, {search_term}, high quality, clear, editorial style"
            negative_prompt = "blurry, low quality, distorted, watermark, text, logo, caption"
            
            ai_image_url = await self._generate_ai_image(enhanced_prompt, negative_prompt)
            
            if ai_image_url:
                print(f"           - ✅ Successfully generated AI image")
                return ai_image_url
            else:
                print(f"           - ⚠️ AI generation failed, falling back to Pixabay")
        
        # Fallback to Pixabay
        print(f"           - Using Pixabay fallback for: '{search_term}'")
        return self._search_pixabay_image(search_term, article_language, used_images)

    def _process_article_images(self, article: EnrichedArticle) -> EnrichedArticle:
        """Process all images in an enriched article."""
        print(f"     - Article: {article.enriched_title[:50]}...")

        # Extract all image placeholders
        placeholders = self._extract_image_placeholders(article.enriched_content)

        if not placeholders:
            print(f"     - No image placeholders found")
            return article

        print(f"     - Found {len(placeholders)} image placeholder(s)")

        # Track used images to avoid duplicates
        used_images = set()
        hero_image_url = None
        updated_content = article.enriched_content
        successful_replacements = 0

        # Get LLM image suggestions if available
        llm_suggestions = getattr(article, "image_suggestions", []) or []
        used_llm_suggestions = set()

        # Run async image generation
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            for i, (full_match, alt_text) in enumerate(placeholders):
                print(f"\n     - Processing placeholder {i+1}/{len(placeholders)}")
                print(f"       Alt text: '{alt_text}'")

                # Strategy: Use alt_text first, then LLM suggestions, then category fallbacks
                search_terms = []

                # Primary: Use alt text if it's descriptive (more than 1 word or specific term)
                if alt_text and len(alt_text.split()) >= 1:
                    search_terms.append(alt_text)
                    print(f"           - Using alt text as search term: '{alt_text}'")

                # Secondary: Try LLM suggestions that haven't been used yet
                available_llm_suggestions = [
                    s for s in llm_suggestions if s not in used_llm_suggestions
                ]
                if available_llm_suggestions:
                    primary_llm_suggestion = available_llm_suggestions[0]
                    search_terms.append(primary_llm_suggestion)
                    used_llm_suggestions.add(primary_llm_suggestion)
                    print(
                        f"           - Using LLM suggestion: '{primary_llm_suggestion}'"
                    )

                # Tertiary: Fallback to category-based terms
                if not search_terms:
                    fallback_terms = self._get_fallback_search_terms(article.categories)
                    search_terms.extend(fallback_terms)
                    print(
                        f"           - Using fallback terms from categories: {fallback_terms}"
                    )

                # Try to get image for the first available search term
                image_url = None
                for term in search_terms:
                    if term in used_llm_suggestions and term != search_terms[0]:
                        # Already used this LLM suggestion
                        continue

                    # Use async method to get image (AI or Pixabay)
                    image_url = loop.run_until_complete(
                        self._get_image_for_search_term_async(
                            term, used_images, article.language
                        )
                    )

                    if image_url:
                        print(f"           - Found image with term: '{term}'")
                        break

                # Mark LLM suggestion as used if we tried it
                if len(search_terms) > 1 and search_terms[1] in llm_suggestions:
                    primary_llm_suggestion = search_terms[1]
                    used_llm_suggestions.add(primary_llm_suggestion)
                    print(
                        f"           - Marked LLM suggestion '{primary_llm_suggestion}' as used"
                    )

                if image_url:
                    # Add to used images set
                    used_images.add(image_url)

                    # Download image locally (works for both AI and Pixabay URLs)
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
        finally:
            # Cleanup async resources
            if self.runware and hasattr(self, '_runware_connected'):
                # Note: Runware SDK doesn't have explicit disconnect, but we can reset the flag
                delattr(self, '_runware_connected')
            loop.close()

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
        
        if self.use_ai_generation:
            print("   - Using AI image generation (Runware) with Pixabay fallback")
        else:
            print("   - Using Pixabay only (AI generation disabled)")

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
                import traceback
                traceback.print_exc()
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

    # Get API keys from environment
    pixabay_key = os.getenv("PIXABAY_API_KEY")
    runware_key = os.getenv("RUNWARE_API_KEY")
    
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
    print(f"- Runware API key: {'✓' if runware_key else '✗'}")
    print(f"- LLM image suggestions: {test_article.image_suggestions}")

    # Create and run the agent
    image_agent = ArticleImageGeneratorAgent(
        pixabay_api_key=pixabay_key,
        runware_api_key=runware_key,
        use_ai_generation=True  # Enable AI generation for test
    )

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