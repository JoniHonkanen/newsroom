# api/admin/compositions.py
from fastapi import APIRouter, HTTPException
import psycopg
from pydantic import BaseModel

from utils.database import get_db_connection

router = APIRouter()


# FRAGMENTS for prompt construction
class PromptFragment(BaseModel):
    name: str
    content: str


# PROMPT FRAGMENTS ROUTES
# GET ALL FRAGMENTS FOR CREATING PROMPTS
@router.get("/prompt-fragments")
async def get_prompt_fragments():
    """Hae kaikki prompt-fragmentit"""
    print("ASDASDASD")
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, name, content, is_system, created_at 
                FROM prompt_fragments 
                ORDER BY is_system DESC, name ASC
            """
            )
            rows = await cur.fetchall()
            print(rows)

            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "content": row[2],
                    "is_system": row[3],
                    "created_at": row[4].isoformat() if row[4] else None,
                }
                for row in rows
            ]


# CREATE NEW FRAGMENT
@router.post("/prompt-fragments")
async def create_prompt_fragment(fragment: PromptFragment):
    """Luo uusi prompt-fragmentti"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.execute(
                    """
                    INSERT INTO prompt_fragments (name, content, is_system)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """,
                    (fragment.name, fragment.content, False),
                )

                fragment_id = (await cur.fetchone())[0]
                await conn.commit()

                return {
                    "message": f"Fragment '{fragment.name}' created",
                    "id": fragment_id,
                }
            except psycopg.IntegrityError:
                raise HTTPException(
                    status_code=400, detail="Fragment name already exists"
                )


# DELETE FRAGMENT
@router.delete("/prompt-fragments/{fragment_id}")
async def delete_prompt_fragment(fragment_id: int):
    """Poista prompt-fragmentti (vain käyttäjän luomat)"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            # Check if fragment exists and is not system
            await cur.execute(
                """
                SELECT is_system FROM prompt_fragments WHERE id = %s
            """,
                (fragment_id,),
            )

            result = await cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Fragment not found")

            if result[0]:  # is_system = True
                raise HTTPException(
                    status_code=403, detail="Cannot delete system fragment"
                )

            # Check if used in ANY composition
            await cur.execute(
                """
                SELECT name FROM prompt_compositions 
                WHERE %s = ANY(fragment_ids)
            """,
                (fragment_id,),
            )

            compositions = await cur.fetchall()
            if compositions:
                composition_names = [row[0] for row in compositions]
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot delete fragment: used in compositions: {', '.join(composition_names)}",
                )

            # Delete fragment
            await cur.execute(
                """
                DELETE FROM prompt_fragments WHERE id = %s
            """,
                (fragment_id,),
            )

            await conn.commit()
            return {"message": "Fragment deleted"}
