# api/admin/compositions.py
from fastapi import APIRouter, HTTPException
import psycopg
from pydantic import BaseModel

from utils.database import get_db_connection

router = APIRouter()


class EthicalPersona(BaseModel):
    name: str
    content: str


# ETHICAL PERSONAS ROUTES
# GET ALL PERSONAS
@router.get("/ethical-personas")
async def get_ethical_personas():
    """Hae kaikki eettiset persoonat"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, name, content, is_system 
                FROM prompt_ethical_personas 
                ORDER BY is_system DESC, name ASC;
            """
            )
            rows = await cur.fetchall()

            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "content": row[2],
                    "is_system": row[3],
                }
                for row in rows
            ]


# CREATE NEW PERSONA
@router.post("/ethical-personas")
async def create_ethical_persona(persona: EthicalPersona):
    """Luo uusi eettinen persoona"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.execute(
                    """
                    INSERT INTO prompt_ethical_personas (name, content, is_system)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """,
                    (persona.name, persona.content, False),
                )

                persona_id = (await cur.fetchone())[0]
                await conn.commit()

                return {
                    "message": f"Ethical persona '{persona.name}' created",
                    "id": persona_id,
                }
            except psycopg.IntegrityError:
                raise HTTPException(
                    status_code=400, detail="Persona name already exists"
                )


# DELETE PERSONA
@router.delete("/ethical-personas/{persona_id}")
async def delete_ethical_persona(persona_id: int):
    """Poista eettinen persoona (vain käyttäjän luomat)"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            # Check if persona exists and is not system
            await cur.execute(
                """
                SELECT is_system FROM prompt_ethical_personas WHERE id = %s
            """,
                (persona_id,),
            )

            result = await cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Persona not found")

            if result[0]:  # is_system = True
                raise HTTPException(
                    status_code=403, detail="Cannot delete system persona"
                )

            # Check if used in ANY composition (not just active ones)
            await cur.execute(
                """
                SELECT name FROM prompt_compositions 
                WHERE ethical_persona_id = %s
            """,
                (persona_id,),
            )

            compositions = await cur.fetchall()
            if compositions:
                composition_names = [row[0] for row in compositions]
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot delete persona: used in compositions: {', '.join(composition_names)}",
                )

            # Delete persona
            await cur.execute(
                """
                DELETE FROM prompt_ethical_personas WHERE id = %s
            """,
                (persona_id,),
            )

            await conn.commit()
            return {"message": "Persona deleted"}
