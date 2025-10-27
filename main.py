# File: main.py
from dotenv import load_dotenv
from agents.article_content_extractor_agent import ArticleContentExtractorAgent
from agents.article_image_generator_agent import ArticleImageGeneratorAgent
from agents.editor_in_chief_agent import EditorInChiefAgent
from agents.feed_reader_agent import FeedReaderAgent
from agents.interview_agents.email_interview_agent import EmailInterviewExecutionAgent
from agents.interview_agents.phone_interview_agent import PhoneInterviewExecutionAgent
from agents.news_planner_agent import NewsPlannerAgent
from agents.news_storer_agent import NewsStorerAgent
from agents.subtask_agents.article_fixer_agent import ArticleFixerAgent
from agents.subtask_agents.editor_in_chief_validate_fixes import FixValidationAgent
from agents.subtask_agents.interview_planning_agent import InterviewPlanningAgent
from agents.subtask_agents.publisher_agent import ArticlePublisherAgent
from agents.subtask_agents.reject_agent import ArticleRejectAgent
from agents.web_search_agent import WebSearchAgent
from agents.article_generator_agent import ArticleGeneratorAgent
from agents.article_storer_agent import ArticleStorerAgent
from agents.contacts_extractor_agent import ContactsExtractorAgent
from schemas.feed_schema import NewsFeedConfig
from schemas.agent_state import AgentState
from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model
import yaml
import time
import os
import threading
from email_processor import check_and_process_emails

# THIS IS THE AGENT SYSTEM THAT GENERATES, REVIEWS, EDITS, INTERVIEWS AND PUBLISHES NEWS ARTICLES

# Load environment variables from .env file
load_dotenv()
# This is what we use to connect to the PostgreSQL database
# During test phase, we use docker-compose to set up the database
db_dsn = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
print("DSN:", db_dsn)

llm = init_chat_model("gpt-4o-mini", model_provider="openai")

NEWS_PLANNING_PROMPT = "Plan article: {article_text} / {published_date}"

# read rss feeds from config file
with open("newsfeeds.yaml") as f:
    config = yaml.safe_load(f)
feeds = [NewsFeedConfig(**feed) for feed in config["feeds"]]


def run_email_checker():
    """Tarkista sähköpostit 15 min välein taustasäikeenä"""
    print("🔍 Email Processor starting in background...")
    print("⏰ Checking emails every 15 minutes")
    print("")

    while True:
        try:
            print(
                f"📧 [{time.strftime('%Y-%m-%d %H:%M:%S')}] Checking for new email replies..."
            )
            check_and_process_emails()
            print("✅ Email check completed successfully")
        except Exception as e:
            print(f"❌ Email check failed: {e}")

        print("⏳ Sleeping for 15 minutes...")
        print("")
        time.sleep(900)  # 15 min


def has_articles(state):
    """Check if the state contains articles to process."""
    articles = state.articles  # Käytä suoraan, ei getattr
    if articles:
        return "continue"  # Yleinen "jatka" arvo
    return "end"


# Editor in Chief decision -> "publish", "interview", "revise", "reject"
def get_editorial_decision(state: AgentState):
    """Route based on editor-in-chief review result."""
    if hasattr(state, "review_result") and state.review_result:
        return state.review_result.editorial_decision
    return "reject"


# Get the interview method - email or phone
def get_interview_method(state: AgentState):
    # TODO:: DO BETTER ERROR HANDLING HERE
    if hasattr(state, "interview_plan") and state.interview_plan:
        return state.interview_plan.interview_method
    return "unknown"


# THIS IS WHAT WE USE HANDLE ONE ARTICLE AT A TIME
# INCLUDES PUBLISHING, INTERVIEWS, REVISIONS...etc..
def create_editorial_subgraph():
    """Create subgraph for individual article editorial decisions."""
    subgraph = StateGraph(AgentState)

    # Initialize agents using existing ones
    editor_in_chief = EditorInChiefAgent(llm=llm, db_dsn=db_dsn)
    article_fixer = ArticleFixerAgent(
        llm=llm, db_dsn=db_dsn
    )  # For interview/revision planning
    article_publisher = ArticlePublisherAgent(db_dsn=db_dsn)  # For publishing
    article_fix_validator = FixValidationAgent(llm=llm)  # For validating fixes
    article_rejecter = ArticleRejectAgent(db_dsn=db_dsn)  # For rejecting articles
    # INTERVIEWS
    interview_planner = InterviewPlanningAgent(llm=llm, db_dsn=db_dsn)
    interview_email_executor = EmailInterviewExecutionAgent(db_dsn=db_dsn)
    interview_phone_executor = PhoneInterviewExecutionAgent(db_dsn=db_dsn)

    # Add nodes
    # Editor in Chief reviews the article, and determines if it needs to be published, interviewed, revised or rejected
    subgraph.add_node("editor_in_chief", editor_in_chief.run)
    # If Editor in Chief decides to interview, we create a new plan for it
    subgraph.add_node("interview_planning", interview_planner.run)
    # If Editor in Chief decides to revise the article, we create a new plan for it
    subgraph.add_node("article_fixer", article_fixer.run)
    # If everything is ok, we publish the article
    subgraph.add_node("publish_article", article_publisher.run)
    # If article has been fixed, we validate the fixes
    subgraph.add_node("article_fix_validator", article_fix_validator.run)
    # If article is rejected, we handle the rejection
    subgraph.add_node("article_rejecter", article_rejecter.run)
    # for email interviews, we send the email with questions
    subgraph.add_node("interview_email_executor", interview_email_executor.run)
    subgraph.add_node("interview_phone_executor", interview_phone_executor.run)

    # Start with editor-in-chief decision
    subgraph.add_edge(START, "editor_in_chief")

    # Conditional edges based on editorial decision
    # DO WE NEED TO PUBLISH, INTERVIEW, REVISE OR REJECT?
    subgraph.add_conditional_edges(
        source="editor_in_chief",
        path=get_editorial_decision,
        path_map={
            "publish": "publish_article",
            "interview": "interview_planning",
            "revise": "article_fixer",
            "reject": "article_rejecter",
        },
    )

    # If article have been fixed, we send it back to validation
    # if its ok -> publish, if not -> revise again
    # if iterations over 2, we reject the article
    subgraph.add_edge("article_fixer", "article_fix_validator")
    subgraph.add_conditional_edges(
        source="article_fix_validator",
        path=lambda state: state.review_result.editorial_decision,
        path_map={
            "publish": "publish_article",
            "revise": "article_fixer",  # If still needs revision, go back
            "reject": "article_rejecter",  # If rejected, we end the process
        },
    )

    subgraph.add_conditional_edges(
        source="interview_planning",
        path=get_interview_method,
        path_map={
            "email": "interview_email_executor",
            "phone": "interview_phone_executor",
            "unknown": END,  # fallback
        },
    )

    # Paths lead to END
    subgraph.add_edge("publish_article", END)
    subgraph.add_edge("article_rejecter", END)
    # TODO:: NEED TO CHECK AGAIN AFTER INTERVIEWS ARE DONE... so send to article enhancer (not done...)
    subgraph.add_edge("interview_email_executor", END)
    subgraph.add_edge("interview_phone_executor", END)

    # AFTER THIS WE RETURN TO THE MAIN GRAPH
    # AND FROM THERE WE CHECK IF THERE ARE ANY PENDING INTERVIEWS OR REVISIONS...

    return subgraph.compile()


# We can use this function to process a batch of articles through editorial review
def process_editorial_batch(state: AgentState):
    """Process all enriched articles through editorial review using subgraph."""
    if not hasattr(state, "enriched_articles") or not state.enriched_articles:
        print("No enriched articles to review")
        return state

    editorial_subgraph = create_editorial_subgraph()

    print(f"\n{'='*70}")
    print(f"📊 EDITORIAL BATCH: Processing {len(state.enriched_articles)} articles...")
    print(f"{'='*70}\n")

    for i, article in enumerate(state.enriched_articles):
        try:
            print(f"\n{'-'*70}")
            print(
                f"📰 Article {i+1}/{len(state.enriched_articles)}: {getattr(article, 'enriched_title', 'Untitled')[:50]}..."
            )
            print(f"{'-'*70}")

            article_state = AgentState(current_article=article)
            result_state = editorial_subgraph.invoke(article_state)

            if result_state is None:
                print(f"⚠️ Subgraph returned None for article {i+1}")
                continue

        except Exception as e:
            print(f"\n❌ ERROR in editorial review for article {i+1}:")
            print(f"   Exception: {e}")
            import traceback

            traceback.print_exc()
            continue
    return state


if __name__ == "__main__":
    # START THE WHOLE AGENT THINGS BY COMMAND: python main.py
    feed_reader = FeedReaderAgent(feed_urls=[f.url for f in feeds], max_news=1)
    article_extractor = ArticleContentExtractorAgent()
    news_storer = NewsStorerAgent(db_dsn=db_dsn)
    news_planner = NewsPlannerAgent(
        llm=llm,
    )
    web_search = WebSearchAgent(max_results_per_query=1)
    article_generator = ArticleGeneratorAgent(llm=llm)
    article_image_generator = ArticleImageGeneratorAgent(
        pixabay_api_key=os.getenv("PIXABAY_API_KEY")
    )
    article_storer = ArticleStorerAgent(db_dsn=db_dsn)
    # editor_in_chief = EditorInChiefAgent(llm=llm, db_dsn=db_dsn)

    # Build the state graph for the agents
    graph_builder = StateGraph(AgentState)
    # NODES
    graph_builder.add_node("feed_reader", feed_reader.run)
    graph_builder.add_node("content_extractor", article_extractor.run)
    graph_builder.add_node("contacts_extractor", ContactsExtractorAgent(llm=llm).run)
    graph_builder.add_node("news_storer", news_storer.run)
    graph_builder.add_node("news_planner", news_planner.run)
    graph_builder.add_node("web_search", web_search.run)
    graph_builder.add_node("article_generator", article_generator.run)
    graph_builder.add_node("article_image_generator", article_image_generator.run)
    graph_builder.add_node("article_storer", article_storer.run)

    # FROM THIS WE START EDITORIAL REVIEW -> ONE ARTICLE AT A TIME - SO WE'LL USE A SUBGRAPH
    graph_builder.add_node("editorial_batch", process_editorial_batch)

    # EDGES
    graph_builder.add_edge(START, "feed_reader")
    # if no articles, go to END
    graph_builder.add_conditional_edges(
        source="feed_reader",
        path=has_articles,
        path_map={"continue": "content_extractor", "end": END},
    )
    graph_builder.add_edge("content_extractor", "contacts_extractor")
    graph_builder.add_edge("contacts_extractor", "news_storer")
    # OBS! If there is many same hash articles or embeddings, we (no new articles) go to END
    graph_builder.add_conditional_edges(
        source="news_storer",
        path=has_articles,
        path_map={"continue": "news_planner", "end": END},
    )
    graph_builder.add_edge("news_planner", "web_search")
    graph_builder.add_edge("web_search", "article_generator")
    graph_builder.add_edge("article_generator", "article_image_generator")
    graph_builder.add_edge("article_image_generator", "article_storer")
    graph_builder.add_edge("article_storer", "editorial_batch")
    graph_builder.add_edge("editorial_batch", END)

    graph = graph_builder.compile()

    # Käynnistä email checker taustasäikeenä
    email_thread = threading.Thread(target=run_email_checker, daemon=True)
    email_thread.start()
    print("✅ Email processor background thread started")
    print("")

    # Run the agent graph in a loop to continuously fetch and process news articles
    while True:
        state = AgentState()
        result = graph.invoke(state)
        print("Graph done!")
        time.sleep(120)
