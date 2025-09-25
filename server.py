# server.py
import os
import sys
import logging

# thi server is ment for BUSINESS LOGIC, not for GraphQL (newsroom frontend)

# Lisää root-polku heti alussa
#sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Import routers
from api.admin import personas, compositions, fragments, test_article
from api.twilio import phone_service

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Newsroom API", version="1.0.0", description="Admin + Callbacks + Twilio API"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://*.vercel.app",
        "https://*.loca.lt",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logger.error(f"💥 Validation error: {exc.errors()}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


# ============ INCLUDE ROUTERS ============
app.include_router(personas.router, prefix="/api", tags=["Admin - Personas"])
app.include_router(compositions.router, prefix="/api", tags=["Admin - Compositions"])
app.include_router(fragments.router, prefix="/api", tags=["Admin - Fragments"])
app.include_router(test_article.router, prefix="/api", tags=["Admin - Testing"])

app.include_router(
    phone_service.router, prefix="", tags=["Twilio"]
)  # No prefix for /incoming-call


# ============ CORE ENDPOINTS ============
@app.get("/health")
async def health_check():
    return {"status": "OK", "service": "Newsroom API"}


@app.get("/")
async def root():
    return {
        "message": "🤖 Newsroom API",
        "endpoints": {
            "admin": "/api/*",
            "twilio": "/incoming-call, /media-stream",
            "docs": "/docs",
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("BUSINESS_LOGIC_SERVER", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
