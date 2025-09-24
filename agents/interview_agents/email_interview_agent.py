import os
import smtplib
import uuid
import logging
from email.message import EmailMessage
from typing import Optional, Tuple
import psycopg  # type: ignore
from schemas.agent_state import AgentState
from schemas.interview_schema import InterviewPlan, EmailInterviewPlan
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class EmailInterviewExecutionAgent:
    """Agent that sends interview questions by email and stores them in the database."""

    def __init__(self, db_dsn: str):
        self.db_dsn = db_dsn

    def run(self, state: AgentState) -> AgentState:
        """Main execution method for the agent."""
        try:
            plan: InterviewPlan = state.interview_plan
            email_plan: EmailInterviewPlan = plan.email_plan

            # Use the formatted_email_body directly
            plain_text = email_plan.formatted_email_body
            html_body = self._convert_to_html(email_plan.formatted_email_body)

            # TODO::: THIS IS STILL FOR TESTING... WE USE OUR OWN EMAIL TO CONTACT...
            success, message, msg_id = self._send_email(
                to=os.getenv("CONTACT_PERSON_EMAIL"),
                # to=email_plan.recipient,
                subject=email_plan.subject,
                plain_text=plain_text,
                html_body=html_body,
            )

            print(f"Email send result: {success}, {message}, {msg_id}")

            if success:
                try:
                    email_db_id = self._store_email_to_db(email_plan, msg_id)
                    print(
                        f"✅ Email and questions stored to database with ID: {email_db_id}"
                    )
                except Exception as e:
                    print(f"Failed to store email to database: {e}")
                    # Email was sent but not stored - this is a partial failure

            return state

        except Exception as e:
            logger.error(f"Unexpected error in EmailInterviewExecutionAgent: {e}")
            return state

    @staticmethod
    def generate_message_id(domain: Optional[str] = None) -> str:
        """Generate a unique Message-ID for the email."""
        print("TEHDÄÄN ID!!")
        if domain is None:
            email_addr = os.getenv("EMAIL_ADDRESS_GMAIL")
            domain = email_addr.split("@")[-1]
        unique_id = uuid.uuid4()
        return f"<{unique_id}@{domain}>"

    def _convert_to_html(self, plain_text: str) -> str:
        """Convert formatted_email_body to HTML with compact layout for email clients."""
        html_lines = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            "<meta charset='utf-8'>",
            "</head>",
            "<body style='font-family: Arial, sans-serif; line-height: 1.3; color: #333; margin: 0; padding: 0;'>",
            "<table width='100%' cellpadding='0' cellspacing='0' style='margin: 0; padding: 0;'>",
            "<tr><td style='padding: 10px;'>",
        ]

        # Split into lines and process
        lines = plain_text.split("\n")
        in_list = False
        in_signature = False

        for line in lines:
            line = line.strip()

            # Check if we're starting the signature section
            if line == "Ystävällisin terveisin,":
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(
                    f'<p style="margin: 15px 0 5px 0; font-family: Georgia, serif; font-style: italic; color: #555;">{line}</p>'
                )
                in_signature = True
                continue

            if not line:
                # Empty line - close list if open, minimal break
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                if not in_signature:
                    html_lines.append('<div style="height: 8px;"></div>')

            elif line.startswith("**") and line.endswith(":**"):
                # Topic header like **Energy Markets:**
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                topic = line.replace("**", "").replace(":", "")
                html_lines.append(
                    f'<h3 style="color: #2c3e50; margin: 12px 0 5px 0; font-size: 16px; font-weight: bold;">{topic}:</h3>'
                )

            elif line.startswith("- "):
                # Bullet point - start list if not already started
                if not in_list:
                    html_lines.append(
                        '<ul style="margin: 5px 0 10px 20px; padding: 0;">'
                    )
                    in_list = True
                question = line[2:].strip()
                html_lines.append(
                    f'<li style="margin: 3px 0; padding: 0;">{question}</li>'
                )

            elif line.startswith("http"):
                # URL - close list first if open
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(
                    f'<p style="margin: 8px 0;"><a href="{line}" style="color: #3498db; text-decoration: none;">{line}</a></p>'
                )

            else:
                # Regular paragraph - close list first if open
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False

                if in_signature:
                    # Part of signature
                    html_lines.append(
                        f'<p style="margin: 2px 0; font-family: Georgia, serif; font-style: italic; color: #555;">{line}</p>'
                    )
                else:
                    # Regular content
                    html_lines.append(f'<p style="margin: 6px 0;">{line}</p>')

        # Close any remaining elements
        if in_list:
            html_lines.append("</ul>")

        html_lines.extend(["</td></tr>", "</table>", "</body>", "</html>"])

        return "\n".join(html_lines)

    def _send_email(
        self, to: str, subject: str, plain_text: str, html_body: str
    ) -> Tuple[bool, str, str]:
        """Send the email using SMTP."""
        try:
            email_host = os.environ["EMAIL_HOST_GMAIL"]
            email_port = int(os.environ["EMAIL_PORT"])
            email_address_sender = os.environ["EMAIL_ADDRESS_GMAIL"]
            email_password = os.environ["EMAIL_PASSWORD_GMAIL"]

            logger.info(f"Attempting to send email to: {to}")
            logger.info(f"Subject: {subject}")
            logger.debug(f"Plain text content length: {len(plain_text)} chars")
            logger.debug(f"HTML content length: {len(html_body)} chars")

            msg = EmailMessage()
            msg["From"] = email_address_sender
            msg["To"] = to
            msg["Subject"] = subject

            # Generate and set Message-ID
            msg_id = self.generate_message_id()
            print(f"Generated Message-ID: {msg_id}")
            msg["Message-ID"] = msg_id

            # Set content
            msg.set_content(plain_text)
            msg.add_alternative(html_body, subtype="html")

            # Send email
            with smtplib.SMTP(email_host, email_port) as smtp:
                smtp.starttls()
                smtp.login(email_address_sender, email_password)
                smtp.send_message(msg)

            logger.info("✅ Email sent successfully")
            return True, f"Email sent successfully to {to}", msg_id

        except ValueError as e:
            error_msg = f"Configuration error: {e}"
            logger.error(error_msg)
            return False, error_msg, ""

        except smtplib.SMTPAuthenticationError as e:
            error_msg = f"SMTP authentication failed: {e}"
            logger.error(error_msg)
            return False, error_msg, ""

        except smtplib.SMTPException as e:
            error_msg = f"SMTP error occurred: {e}"
            logger.error(error_msg)
            return False, error_msg, ""

        except Exception as e:
            error_msg = f"Unexpected error sending email: {e}"
            logger.error(error_msg)
            return False, error_msg, ""

    def _store_email_to_db(self, email_plan: EmailInterviewPlan, msg_id: str) -> int:
        """Store the sent email and questions to database."""
        print("Storing email to database...")
        print(email_plan)
        print("TÄÄ ID:")
        print(msg_id)
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    # Insert into email_interview table
                    cur.execute(
                        """
                        INSERT INTO email_interview
                        (news_article_id, interview_decision_id, message_id, recipient, subject, status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        RETURNING id
                        """,
                        (
                            email_plan.news_article_id,
                            getattr(email_plan, "interview_decision_id", None),
                            msg_id,
                            email_plan.recipient,
                            email_plan.subject,
                            "sent",
                        ),
                    )
                    email_id = cur.fetchone()[0]

                    # Insert questions
                    for i, q in enumerate(email_plan.questions, 1):
                        cur.execute(
                            """
                            INSERT INTO email_questions (email_id, topic, question, position)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (email_id, q.topic, q.question, i),
                        )

                    conn.commit()
                    logger.info(
                        f"Stored email with ID {email_id} and {len(email_plan.questions)} questions"
                    )
                    return email_id

        except psycopg.Error as e:
            logger.error(f"Database error storing email: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error storing email to database: {e}")
            raise


if __name__ == "__main__":

    from schemas.interview_schema import InterviewPlan, InterviewQuestion

    # python -m agents.interview_agents.email_interview_agent

    # Create test data based on your mockdata
    questions = [
        InterviewQuestion(
            topic="Taloudellinen kehitys",
            question="Miten arvioitte Patrian vahvan kasvun jatkuvan tulevina vuosina, kun puolustusbudjetit kasvavat globaalisti?",
            position=1,
            priority="high",
            follow_up_potential=True,
        ),
        InterviewQuestion(
            topic="Markkinanäkymät",
            question="Mitkä tekijät vaikuttavat eniten puolustusteollisuuden kysyntään Suomessa ja Euroopassa?",
            position=2,
            priority="high",
            follow_up_potential=True,
        ),
        InterviewQuestion(
            topic="Strategiset hankkeet",
            question="Miten NATO-jäsenyys on vaikuttanut Patrian liiketoimintamahdollisuuksiin ja kansainväliseen yhteistyöhön?",
            position=3,
            priority="medium",
            follow_up_potential=True,
        ),
        InterviewQuestion(
            topic="Kilpailukyky",
            question="Mitkä ovat Patrian tärkeimmät kilpailuedut verrattuna muihin puolustusteollisuuden toimijoihin?",
            position=4,
            priority="medium",
            follow_up_potential=True,
        ),
    ]

    email_plan = EmailInterviewPlan(
        news_article_id=1,
        interview_decision_id=None,
        recipient=os.getenv("CONTACT_PERSON_EMAIL"),
        subject="Kysymyksiä artikkelista: Patrian liikevaihto ja liikevoitto paranivat alkuvuonna",
        questions=questions,
        background_context="Taloudellisen kasvun analyysi puolustusteollisuudessa",
        target_expertise_areas=[
            "puolustusteollisuus",
            "talousanalyysi",
            "markkinanäkymät",
        ],
        interview_focus="Asiantuntijanäkökulma Patrian kasvuun ja puolustusteollisuuden tulevaisuuteen",
        formatted_email_body="""Hei,

Teen journalistista juttua aiheesta "Patrian liikevaihto ja liikevoitto paranivat alkuvuonna". Patrian vahva taloudellinen kehitys ja puolustusbudjettien kasvu herättävät kysymyksiä alan tulevaisuudesta.

Haluaisin kysyä muutaman tarkentavan kysymyksen aiheeseen liittyen:

**Taloudellinen kehitys:**
- Miten arvioitte Patrian vahvan kasvun jatkuvan tulevina vuosina, kun puolustusbudjetit kasvavat globaalisti?

**Markkinanäkymät:**
- Mitkä tekijät vaikuttavat eniten puolustusteollisuuden kysyntään Suomessa ja Euroopassa?

**Strategiset hankkeet:**
- Miten NATO-jäsenyys on vaikuttanut Patrian liiketoimintamahdollisuuksiin ja kansainväliseen yhteistyöhön?

**Kilpailukyky:**
- Mitkä ovat Patrian tärkeimmät kilpailuedut verrattuna muihin puolustusteollisuuden toimijoihin?

Kiitos ajastanne! Vastaukset käsitellään osana tekoälyavusteista tutkimusta, jossa tekoäly toimii journalistina.
https://www.tuni.fi/fi/tutkimus/tekoalyn-johtama-uutistoimitus

Ystävällisin terveisin,

Teppo Tekoälyjournalisti
– tutkimushanke Tampereen yliopisto""",
    )

    interview_plan = InterviewPlan(
        canonical_news_id=1,
        article_id=1,
        interview_method="email",
        email_plan=email_plan,
        phone_plan=None,
        available_contacts=[],
    )

    # Test the agent
    db_dsn = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/newsdb")
    state = type("State", (), {"interview_plan": interview_plan})()

    agent = EmailInterviewExecutionAgent(db_dsn=db_dsn)
    print("🧪 Testing EmailInterviewExecutionAgent...")
    print(f"📧 Sending to: {email_plan.recipient or 'CONTACT_PERSON_EMAIL not set'}")
    print(f"📝 Subject: {email_plan.subject}")
    print(f"❓ Questions: {len(email_plan.questions)}")

    result_state = agent.run(state)

    print(f"\n✅ Results:")
    print(f"  Email sent: {getattr(result_state, 'email_sent', None)}")
    print(f"  Message ID: {getattr(result_state, 'email_message_id', None)}")
    print(f"  Database ID: {getattr(result_state, 'email_db_id', None)}")
