# api/admin/compositions.py
from fastapi import APIRouter, HTTPException
import psycopg
from pydantic import BaseModel
from typing import List

from ...utils.database import get_db_connection

router = APIRouter()


# Pydantic model (kopioi server.py:stä)
class PromptComposition(BaseModel):
    name: str
    ethical_persona_id: int
    fragment_ids: List[int] = []


@router.get("/prompt-compositions")
async def get_prompt_compositions():
    """Hae kaikki prompt-kokoonpanot"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, name, ethical_persona_id, fragment_ids, is_active, created_at
                FROM prompt_compositions 
                ORDER BY is_active DESC, created_at DESC
            """
            )
            rows = await cur.fetchall()

            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "ethical_persona_id": row[2],
                    "fragment_ids": row[3] or [],
                    "is_active": row[4],
                    "created_at": row[5].isoformat() if row[5] else None,
                }
                for row in rows
            ]


@router.post("/prompt-compositions")
async def create_prompt_composition(composition: PromptComposition):
    """Luo uusi prompt-kokoonpano"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            # Validate persona exists
            await cur.execute(
                """
                SELECT COUNT(*) FROM prompt_ethical_personas WHERE id = %s
            """,
                (composition.ethical_persona_id,),
            )

            if (await cur.fetchone())[0] == 0:
                raise HTTPException(status_code=400, detail="Ethical persona not found")

            # Validate fragments exist (if any)
            if composition.fragment_ids:
                await cur.execute(
                    """
                    SELECT COUNT(*) FROM prompt_fragments WHERE id = ANY(%s)
                """,
                    (composition.fragment_ids,),
                )

                if (await cur.fetchone())[0] != len(composition.fragment_ids):
                    raise HTTPException(
                        status_code=400, detail="One or more fragments not found"
                    )

            try:
                await cur.execute(
                    """
                    INSERT INTO prompt_compositions (name, ethical_persona_id, fragment_ids, is_active)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """,
                    (
                        composition.name,
                        composition.ethical_persona_id,
                        composition.fragment_ids,
                        False,
                    ),
                )

                composition_id = (await cur.fetchone())[0]
                await conn.commit()

                return {
                    "message": f"Composition '{composition.name}' created",
                    "id": composition_id,
                }
            except psycopg.IntegrityError:
                raise HTTPException(
                    status_code=400, detail="Composition name already exists"
                )


@router.put("/prompt-compositions/{composition_id}/activate")
async def activate_composition(composition_id: int):
    """Aktivoi tietty kokoonpano (deaktivoi muut)"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            # Check composition exists
            await cur.execute(
                """
                SELECT name FROM prompt_compositions WHERE id = %s
            """,
                (composition_id,),
            )

            result = await cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Composition not found")

            composition_name = result[0]

            # Deactivate all compositions
            await cur.execute(
                """
                UPDATE prompt_compositions SET is_active = false, updated_at = NOW()
                WHERE is_active = true
            """
            )

            # Activate this composition
            await cur.execute(
                """
                UPDATE prompt_compositions 
                SET is_active = true, updated_at = NOW()
                WHERE id = %s
            """,
                (composition_id,),
            )

            await conn.commit()
            return {"message": f"Composition '{composition_name}' activated"}


@router.delete("/prompt-compositions/{composition_id}")
async def delete_composition(composition_id: int):
    """Poista kokoonpano"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            # Tarkista että kokoonpano on olemassa
            await cur.execute(
                "SELECT name FROM prompt_compositions WHERE id = %s", (composition_id,)
            )

            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="Composition not found")

            # Poista kokoonpano
            await cur.execute(
                "DELETE FROM prompt_compositions WHERE id = %s", (composition_id,)
            )

            await conn.commit()
            return {"message": "Composition deleted"}
