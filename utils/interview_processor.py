# utils/interview_processor.py
import asyncio
import logging
from typing import List, Dict, Any, Optional

from integrations.phone_interview_integration import enrich_article_with_phone_call

logger = logging.getLogger(__name__)


async def process_call_ended(article_id: int, interview_content: List[Dict[str, Any]]) -> Optional[Any]:
    """Kick off article enrichment with the interview content without blocking the event loop."""
    # Build a simple transcript text
    interview_text = "\n".join([
        f"{t.get('speaker')}: {t.get('text')}" for t in interview_content
    ])

    logger.info(
        "▶️ Starting enrichment for article %s (turns=%d)", article_id, len(interview_content)
    )
    loop = asyncio.get_running_loop()
    try:
        # Run potentially blocking sync function on a thread, with a generous timeout
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None, enrich_article_with_phone_call, str(article_id), interview_text
            ),
            timeout=300,
        )
        logger.info("✅ Enrichment done for article %s", article_id)
        return result
    except asyncio.TimeoutError:
        logger.error("⏱️ Enrichment timed out for article %s", article_id)
        return None
    except Exception as e:
        logger.exception("❌ Enrichment failed for article %s: %s", article_id, e)
        return None