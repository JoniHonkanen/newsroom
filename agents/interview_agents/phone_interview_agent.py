import json
import os
from psycopg.types.json import Json as PsycoJson
import requests
import logging
from typing import Optional, Any
import psycopg
from schemas.agent_state import AgentState
from schemas.interview_schema import InterviewPlan, PhoneInterviewPlan
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class PhoneInterviewExecutionAgent:
    """Agent that executes phone interviews via Twilio/OpenAI integration."""

    def __init__(self, db_dsn: str):
        self.db_dsn = db_dsn
        self.phone_server_url = os.getenv("PHONE_SERVER_URL")

    def run(self, state: AgentState) -> AgentState:
        """Main execution method for phone interviews."""
        try:
            plan: InterviewPlan = state.interview_plan
            phone_plan: PhoneInterviewPlan = plan.phone_plan
            phone_script_json = phone_plan.phone_script_json

            # Initiate the call
            success, call_sid, message = self._trigger_phone_call(
                phone_plan, phone_script_json, plan.article_id
            )
            if success:
                try:
                    # Store phone interview to database
                    phone_db_id = self._store_phone_interview_to_db(
                        phone_plan,
                        call_sid,
                        phone_script_json,
                        plan.canonical_news_id,
                        plan.article_id,
                    )
                    logger.info(
                        f"✅ Phone interview stored to database with ID: {phone_db_id}"
                    )
                    logger.info(
                        f"✅ Phone call initiated successfully, SID: {call_sid}"
                    )

                except Exception as e:
                    logger.error(f"Failed to store phone interview to database: {e}")
            else:
                logger.error(f"❌ Phone call failed: {message}")

            return state  # Palauta state muuttamattomana, kuten EmailInterviewExecutionAgent

        except Exception as e:
            logger.error(f"Unexpected error in PhoneInterviewExecutionAgent: {e}")
            return state

    def _trigger_phone_call(
        self, phone_plan: PhoneInterviewPlan, phone_script_json: dict, article_id: int
    ) -> tuple[bool, Optional[str], str]:
        """Trigger the phone call using structured JSON script."""
        try:
            # Hae language phone_script_json:sta
            language = phone_script_json.get("language", "fi")

            # payload = {
            #    "phone_number": phone_plan.to_number,
            #    "language": language,
            #    "phone_script_json": phone_script_json,
            #    "article_id": article_id,
            # }
            payload = {
                "phone_number": os.getenv("CONTACT_PERSON_PHONE"),
                "language": language,
                "phone_script_json": phone_script_json,
                "article_id": article_id,
            }

            print("PAYLOAD")
            print(payload)

            response = requests.post(
                f"{self.phone_server_url}/start-interview", json=payload, timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                call_sid = data.get("call_sid", "unknown")
                logger.info(
                    f"✅ Phone interview initiated successfully, SID: {call_sid}"
                )
                return True, call_sid, "Phone interview initiated successfully"
            else:
                error_msg = f"Phone server returned status {response.status_code}"
                logger.error(error_msg)
                return False, None, error_msg

        except requests.RequestException as e:
            error_msg = f"Failed to connect to phone server: {e}"
            logger.error(error_msg)
            return False, None, error_msg

    def _store_phone_interview_to_db(
        self,
        phone_plan: PhoneInterviewPlan,
        call_sid: str,
        phone_script_json: dict,
        canonical_news_id: int,
        news_article_id: int,
    ) -> int:
        """Store the phone interview to database."""
        try:
            # Hae tiedot phone_script_json:sta
            language = phone_script_json.get("language", "fi")
            instructions = phone_script_json.get("instructions", "")

            logger.info(
                f"Storing phone interview to DB: article_id={news_article_id}, to_number={phone_plan.to_number}, lang={language}"
            )

            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO phone_interview
                        (news_article_id, interview_decision_id, to_number, from_number, status, phone_script_json)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        RETURNING id
                        """,
                        (
                            news_article_id,
                            getattr(phone_plan, "interview_decision_id", None),
                            phone_plan.to_number,
                            phone_plan.from_number,
                            "initiated",
                            json.dumps(phone_script_json, ensure_ascii=False),
                        ),
                    )
                    phone_id = cur.fetchone()[0]

                    cur.execute(
                        """
                        INSERT INTO phone_interview_attempt 
                        (phone_interview_id, started_at, status)
                        VALUES (%s, NOW(), %s)
                        """,
                        (phone_id, f"twilio_sid:{call_sid}"),
                    )

                    conn.commit()
                    logger.info(
                        f"Stored phone interview with ID {phone_id} for article {news_article_id}"
                    )
                    return phone_id

        except psycopg.Error as e:
            logger.error(f"Database error storing phone interview: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error storing phone interview to database: {e}")
            raise


if __name__ == "__main__":
    import os
    from schemas.interview_schema import InterviewPlan, PhoneInterviewPlan

    # RUN THIS TEST WITH A COMMAND:
    # python -m agents.interview_agents.phone_interview_agent

    # Mock database operations for testing
    def mock_store_phone_interview_to_db(
        self,
        phone_plan,
        call_sid,
        phone_script_json,
        canonical_news_id,
        news_article_id,
    ):
        """Mock database storage - return fake ID"""
        print(f"🎭 MOCK: Would store phone interview to DB")
        print(f"     canonical_news_id: {canonical_news_id}")
        print(f"     news_article_id: {news_article_id}")
        print(f"     to_number: {phone_plan.to_number}")
        print(f"     call_sid: {call_sid}")
        print(f"     language: {phone_script_json.get('language')}")
        return 999  # Fake database ID

    # Patch PhoneInterviewExecutionAgent to use mock database only (test-only)
    # PhoneInterviewExecutionAgent._store_phone_interview_to_db = (
    #     mock_store_phone_interview_to_db
    # )

    # Luo oikea OpenAI Realtime API -muotoinen phone_script_json
    phone_script_json = {
        "role": "system",
        "rules": [
            "Älä vastaa omiin kysymyksiisi. Kun haastateltava on valmis, kysy seuraava kysymys.",
            "Puhu vain suomea koko haastattelun ajan.",
            "Kysy vain yksi kysymys kerrallaan.",
            "Lopetuksen jälkeen pyydä sulkemaan puhelu",
        ],
        "voice": "nova",
        "language": "fi",
        "temperature": 0.7,
        "instructions": "Olet Tampereen yliopiston tekoäly, joka tekee haastattelun aiheesta: Lappeenrannan kaupunki poisti uponneen lautan Luukkaansalmesta navigaatioturvallisuuden varmistamiseksi.\nAloita tervehdyksellä ja kerro haastateltavalle, että kyseessä on tekoälyhaastattelu.\nKysy lupa jatkaa, ja esitä sitten kysymykset yksi kerrallaan.\nOdota aina vastaus ennen seuraavaa kysymystä.\nPysy suomen kielessä ja lopuksi kiitä haastattelusta. Älä vaihda kieltä toiseen missään vaiheessa, sillä kielenä on Suomi",
        "questions_data": [
            {
                "text": "Miten uponneen lautan poistaminen Luukkaansalmesta vaikuttaa alueen ympäristönsuojelutoimiin?",
                "topic": "Ympäristöpolitiikka",
                "position": 1,
            },
            {
                "text": "Miksi navigaatioturvallisuus on erityisen tärkeä kysymys Luukkaansalmessa?",
                "topic": "Julki turvallisuus",
                "position": 2,
            },
            {
                "text": "Miten paikallisyhteisö on reagoinut uponneen lautan poistamiseen?",
                "topic": "Yleinen",
                "position": 3,
            },
        ],
    }

    # Yksinkertaistettu PhoneInterviewPlan
    phone_plan = PhoneInterviewPlan(
        to_number=os.getenv("CONTACT_PERSON_PHONE"),
        from_number=None,
        phone_script_json=phone_script_json,
    )

    # InterviewPlan wrapper
    interview_plan = InterviewPlan(
        canonical_news_id=12345,  # Mock ID - ei tallenneta oikeasti
        article_id=12345,
        interview_method="phone",
        email_plan=None,
        phone_plan=phone_plan,
        available_contacts=[],
    )

    state = type("State", (), {"interview_plan": interview_plan})()

    # Käytä patchattua agenttia
    agent = PhoneInterviewExecutionAgent(db_dsn="mock://database")
    print("🧪 Testing PhoneInterviewExecutionAgent (REAL PHONE CALL)...")
    print(f"📞 Calling: {phone_plan.to_number}")
    print(f"🎙️ Language: {phone_script_json['language']}")
    print(f"❓ Questions: {len(phone_script_json['questions_data'])}")

    result_state = agent.run(state)

    print(f"\n✅ REAL CALL RESULTS:")
    print(f"  Phone call attempted to: {phone_plan.to_number}")
    print(f"  State returned correctly: {result_state == state}")
    print(f"  Interview plan preserved: {hasattr(result_state, 'interview_plan')}")
    if hasattr(result_state, "interview_plan") and result_state.interview_plan:
        print(f"  Method: {result_state.interview_plan.interview_method}")
    print("  Check server logs to see actual call results and any returned values")
