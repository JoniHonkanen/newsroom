# Purpose:
#   This agent regularly fetches a list of configured RSS feeds, detects new or
#   updated content, and extracts new articles since the last check. The agent
#   is optimized to avoid duplicate processing and unnecessary bandwidth usage.
# How it works:
#   - For each RSS feed, it maintains a persistent FeedState tracking:
#       * HTTP headers (Last-Modified, ETag) for efficient conditional requests
#       * The unique identifier (GUID/id/link) of the latest processed article
#   - The agent sends conditional HTTP GET requests using 'If-Modified-Since'
#     and 'If-None-Match'. If the feed has not changed (HTTP 304), nothing is done.
#   - If there is a change (HTTP 200), the agent parses the feed and only processes
#     articles that are new since the last run, identified by their unique id.
#   - The agent never relies solely on feed-level metadata (e.g. lastBuildDate),
#     but always deduplicates using article-level GUIDs or similar.
#   - Results are appended to a shared AgentState, for downstream processing

from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.feed_schema import FeedState, CanonicalArticle
import feedparser  # type: ignore
import requests
from datetime import datetime, timezone
from typing import Any, Dict, List


# This use two states, agent state and feed state
# FeedState is used to keep track of if rss feed has been updated, last modified, etag, etc.
class FeedReaderAgent(BaseAgent):
    """Agent that reads RSS feeds and extracts new articles.
    If the feed has not changed since last check, it does nothing.
    If the feed has changed, it parses the feed and extracts new articles
    """

    def __init__(self, feed_urls: List[str], max_news: int = 3):
        super().__init__(llm=None, prompt=None, name="FeedReaderAgent")
        self.feed_urls = feed_urls
        self.max_news = max_news
        self.feed_states: Dict[str, FeedState] = {}

    def run(self, state: AgentState) -> AgentState:
        """Run the agent to fetch and process RSS feeds."""
        for url in self.feed_urls:
            try:
                # Get or initialize feed state
                feed_state = self.feed_states.get(url, FeedState(url=url))

                # Build HTTP conditional GET headers if values available
                headers = {}
                if feed_state.last_modified:
                    headers["If-Modified-Since"] = feed_state.last_modified
                if feed_state.etag:
                    headers["If-None-Match"] = feed_state.etag

                resp = requests.get(url, headers=headers, timeout=15)
                resp.raise_for_status()  # Raise an error for bad responses
                feed_state.last_checked = datetime.now(timezone.utc).isoformat()
                print(f"{url}: HTTP status {resp.status_code}")

                if resp.status_code == 304:
                    # No change in feed since last fetch, nothing to process
                    feed_state.updated = False
                    print(f"{url}: No changes (304 Not Modified).")
                    self.feed_states[url] = feed_state
                    continue

                # Feed changed (200 OK), so parse it
                feed_state.updated = True
                feed_state.last_modified = resp.headers.get("Last-Modified")
                feed_state.etag = resp.headers.get("ETag")

                feed = feedparser.parse(resp.content)
                articles = self.parse_feed_entries(feed, self.max_news)
                # Always process articles oldest-to-newest
                articles.sort(key=lambda a: a["published_at"])  # Korjattu kenttä

                # Find only new articles (not yet processed)
                new_articles = []
                last_processed_id = feed_state.last_processed_id
                found_last = False

                for article in articles:
                    if last_processed_id and article["unique_id"] == last_processed_id:
                        found_last = True
                        continue  # Skip already processed articles
                    if found_last or not last_processed_id:
                        new_articles.append(article)

                if last_processed_id and not found_last:
                    print(
                        f"Warning: Last processed ID '{last_processed_id}' not found in feed. "
                        f"Assuming all {len(articles)} fetched articles are new."
                    )
                    new_articles = articles

                # On first run, just set last_processed_id so we don't reprocess old articles
                if not last_processed_id:
                    if articles:
                        feed_state.last_processed_id = articles[-1]["unique_id"]
                elif new_articles:
                    feed_state.last_processed_id = new_articles[-1]["unique_id"]

                # Convert dict articles to CanonicalArticle objects
                canonical_articles = [
                    CanonicalArticle(**article) for article in new_articles
                ]

                # Extend shared state with only new articles
                state.articles.extend(canonical_articles)
                self.feed_states[url] = feed_state

                # Print summary
                if new_articles:
                    print(f"{url}: {len(new_articles)} new articles found:")
                    for art in new_articles:
                        print(
                            f"- {art['published_at']} {art['title']}"
                        )  # Korjattu kenttä
                else:
                    print(f"{url}: Feed updated, but no new articles.")
            except Exception as e:
                print(f"Error processing {url}: {e}")
                continue
        return state

    @staticmethod
    def parse_feed_entries(feed, max_news: int) -> List[Dict[str, Any]]:
        """Parse RSS feed entries into a list of articles."""
        news_list = []
        for entry in feed.entries[:max_news]:
            title = FeedReaderAgent.clean_text(entry.get("title", "No title"))
            summary = FeedReaderAgent.clean_text(entry.get("summary", "No summary"))
            published_at = FeedReaderAgent.parse_rss_datetime(entry)
            link = entry.get("link", "No link")
            unique_id = FeedReaderAgent.extract_unique_id(entry)
            news_list.append(
                {
                    "title": title,
                    "summary": summary,
                    "published_at": published_at,
                    "link": link,
                    "unique_id": unique_id,
                }
            )
        return news_list

    @staticmethod
    def extract_unique_id(entry: Dict[str, Any]) -> str:
        """Extract a unique identifier for the RSS entry."""
        return (
            entry.get("id")
            or entry.get("guid")
            or entry.get("link")
            or f"{entry.get('title','')}_{entry.get('published','')}"
        )

    # Clean up text by removing unwanted characters
    @staticmethod
    def clean_text(text: str) -> str:
        """Clean up text by removing unwanted characters."""
        return (
            text.replace("\u00ad", "")
            .replace("\u200b", "")
            .replace("\xa0", " ")
            .strip()
        )

    # Parse the published date from the RSS entry, returning ISO format
    @staticmethod
    def parse_rss_datetime(entry) -> str:
        """Parse the published date from the RSS entry, returning ISO format."""
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")
        return "1970-01-01T00:00:00Z"


if __name__ == "__main__":
    from schemas.agent_state import AgentState

    # This is first agent, which fetches news from RSS feeds
    # max_news is the maximum number of new news articles to fetch from each feed

    # To run this agent, you can use the command:
    # python -m agents.feed_reader_agent

    TEST_FEED_URL = "https://yle.fi/rss/uutiset/tuoreimmat"
    agent = FeedReaderAgent(feed_urls=[TEST_FEED_URL], max_news=3)

    # Mockup state for testing
    state = AgentState()

    print("🧪 Testing FeedReaderAgent with Yle RSS feed...")
    result_state = agent.run(state)

    print("\nTest Results:")
    print(
        f"Fetched {len(result_state.articles)} CanonicalArticle articles from feed '{TEST_FEED_URL}'"
    )
    for i, article in enumerate(result_state.articles, 1):
        print(f"{i}. {article.title}")
        print(f"   Link: {article.link}")
        print(f"   Published: {article.published_at}")
        print(f"   Summary: {article.summary[:100]}...")
        print(f"   Unique ID: {article.unique_id}")
