# graphql_server.py
import os
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import strawberry
from dotenv import load_dotenv

from news_graphql.resolvers import Query
load_dotenv()

# THIS IS THE GRAPHQL SERVER FOR THE NEWSROOM FRONTEND

app = FastAPI(title="News GraphQL API")
# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://gptnewsroom.fi",
        "https://www.gptnewsroom.fi",
        "https://newsroom-production-frontend-9nk2ur374-joni-honkanens-projects.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# GraphQL schema
schema = strawberry.Schema(query=Query)
app.include_router(GraphQLRouter(schema), prefix="/graphql")

# Tarkista että kansio on olemassa ennen mounttausta
static_dir = os.getenv("STATIC_FILE_PATH", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    print(f"Warning: Static directory '{static_dir}' not found - skipping static files")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("GRAPHQL_SERVER", 4000))
    uvicorn.run("graphql_server:app", host="0.0.0.0", port=port, reload=True)
