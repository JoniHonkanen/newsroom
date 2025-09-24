# graphql_main.py
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter
import strawberry

from graphql.resolvers import Query
from graphql.database import get_db_pool, close_db_pool

app = FastAPI(title="News GraphQL API")

# GraphQL schema  
schema = strawberry.Schema(query=Query)
app.include_router(GraphQLRouter(schema), prefix="/graphql")

# Static files
app.mount("/static", StaticFiles(directory="static"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("graphql_main:app", host="0.0.0.0", port=4000)