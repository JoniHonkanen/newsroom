# utils/interview_processor.py
async def process_call_ended(article_id: int, interview_content: list):
    """Internal function - no HTTP needed"""
    interview_text = "\n".join([f"{t['speaker']}: {t['text']}" for t in interview_content])
    result = enrich_article_with_phone_call(str(article_id), interview_text)
    return result