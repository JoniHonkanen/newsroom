#!/usr/bin/env python3
"""
Email Processor - Reads email replies -> start enrichment process
"""
import os
import email
from imapclient import IMAPClient
from email.message import Message
from dotenv import load_dotenv
from typing import Any, Dict, List
from mailparser_reply import EmailReplyParser

import psycopg
from integrations.article_enrichment_integration import enrich_article_with_email_reply

# TODO:: NEEDS TESTING!!!

# THIS WILL WORK AS CRON JOB
# It will read email replies from a specific folder (e.g., "INBOX") and process them
# This calls integrations/article_enrichment_integration.py to enrich the article which is linked to article_enricher_agent


# DATABASE FUNCTIONS (PostgreSQL versions)
def init_db(db_dsn: str = None):
    """Initialize PostgreSQL database connection"""
    if db_dsn is None:
        db_dsn = os.getenv("DATABASE_URL")
        if not db_dsn:
            user = os.getenv("DB_USER")
            password = os.getenv("DB_PASSWORD")
            host = os.getenv("DB_HOST", "localhost")
            port = os.getenv("DB_PORT", "5432")
            name = os.getenv("DB_NAME")
            if user and password and name:
                db_dsn = f"postgresql://{user}:{password}@{host}:{port}/{name}"
    if not db_dsn:
        raise RuntimeError(
            "DATABASE_URL not set and DB_* vars missing; cannot connect to DB"
        )
    return psycopg.connect(db_dsn)


def store_reply(conn, reply_dict):
    print("TALLENNETAAN VASTAUS...")
    print("Storing reply:", reply_dict)
    with conn.cursor() as cur:
        # check if uid already exists in email_replies
        cur.execute(
            "SELECT id FROM email_replies WHERE uid = %s", (str(reply_dict["uid"]),)
        )
        if cur.fetchone():
            print(f"UID {reply_dict['uid']} already exists – skipping insert.")
            return None, None, reply_dict

        # check if in_reply_to exists in email_interview
        cur.execute(
            "SELECT id FROM email_interview WHERE message_id = %s",
            (reply_dict["in_reply_to"],),
        )
        row = cur.fetchone()
        email_id = row[0] if row else None

        cur.execute(
            """INSERT INTO email_replies
               (uid, email_id, from_address, in_reply_to, body, received_at)
               VALUES (%s, %s, %s, %s, %s, now())""",
            (
                reply_dict["uid"],
                email_id,
                reply_dict["from"],
                reply_dict["in_reply_to"],
                reply_dict["body"],
            ),
        )
        conn.commit()
        return cur.rowcount, email_id, reply_dict


def fetch_full_email_thread(conn, message_id: str) -> dict:
    print("fetch_full_email_thread!!!!")
    with conn.cursor() as cur:
        # Hae alkuperäinen email_interview
        cur.execute(
            """
            SELECT id, recipient, subject, sent_at
            FROM email_interview
            WHERE message_id = %s
        """,
            (message_id,),
        )
        row = cur.fetchone()
        print("Row fetched:", row)
        if not row:
            return {}

        email_id, recipient, subject, sent_at = row

        # Hae kysymykset email_questions taulusta
        cur.execute(
            """
            SELECT topic, question, position
            FROM email_questions
            WHERE email_id = %s
            ORDER BY position
        """,
            (email_id,),
        )
        questions = cur.fetchall()

        # Hae kaikki vastaukset email_replies taulusta
        cur.execute(
            """
            SELECT from_address, body, received_at
            FROM email_replies
            WHERE email_id = %s
            ORDER BY received_at
        """,
            (email_id,),
        )
        replies = cur.fetchall()

        return {
            "message_id": message_id,
            "recipient": recipient,
            "subject": subject,
            "sent_at": sent_at,
            "questions": [
                {"topic": topic, "question": question, "position": position}
                for topic, question, position in questions
            ],
            "replies": [
                {"from": sender, "body": body, "received_at": ts}
                for sender, body, ts in replies
            ],
        }


load_dotenv()

parser = EmailReplyParser(languages=["en", "fi"])


def read_email_tool(
    folder: str = "INBOX", unseen_only: bool = True, conn=None
) -> List[Dict[str, Any]]:
    if conn is None:
        conn = init_db()

    print("Reading emails...")
    host: str = os.environ["IMAP_HOST_GMAIL"]
    port_str: str = os.environ["IMAP_PORT"]
    user: str = os.environ["EMAIL_ADDRESS_GMAIL"]
    pwd: str = os.environ["EMAIL_PASSWORD_GMAIL"]

    try:
        port: int = int(port_str)
    except ValueError:
        raise ValueError("Invalid IMAP_PORT (must be an integer)")

    with IMAPClient(host, port) as client:
        client.login(user, pwd)

        available_folders = [f[2] for f in client.list_folders()]
        print(f"Available folders: {available_folders}")
        if folder not in available_folders:
            raise ValueError(
                f"Folder '{folder}' not found. Available folders: {available_folders}"
            )
        client.select_folder(folder)

        criteria = "UNSEEN" if unseen_only else "ALL"
        print(f"Searching for emails with criteria: {criteria}")
        uids = client.search(criteria)
        if not uids:
            return []

        uids = uids[-5:]
        print(f"Found {len(uids)} emails, processing the last 5...")
        result: List[Dict[str, Any]] = []

        for uid, data in client.fetch(uids, ["RFC822"]).items():
            raw = data.get(b"RFC822")
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(raw)

            if not is_reply(msg):
                print("Skipping: not a reply.")
                continue

            raw = _extract_body(msg)
            clean = clean_reply_body(raw)

            print("RAW: \n", raw)
            print("CLEAN: \n", clean)

            reply = {
                "uid": uid,
                "from": msg["From"],
                "subject": msg["Subject"],
                "in_reply_to": msg.get("In-Reply-To"),
                "references_header": msg.get("References"),
                "body": clean,
            }

            # tallenna vastaus ja linkitä alkuperäiseen viestiin
            stored_id, email_id, reply_dict = store_reply(conn, reply)
            if stored_id is None:
                print("Vastaus oli jo tallennettu, ohitetaan.")
                continue

            # id of original message (what we sent and where is all the questions)
            orig_msg_id = reply_dict["in_reply_to"]
            if email_id is None:
                print("Ei alkuperäistä viestiä, ei linkitetty.")
                # ota ensimmäinen token references_headerista
                tokens = reply_dict["references_header"].split()
                if tokens:
                    orig_msg_id = tokens[0]

            thread_data = fetch_full_email_thread(conn, orig_msg_id)
            if thread_data:
                # This summary_text is the data we want to send to LLM
                summary_text = build_analysis_input(thread_data)
                print("TÄÄÄÄÄ!!!!!:")
                print(thread_data)

                # ENRICH ARTICLE HERE
                try:
                    result_enrichment = enrich_article_with_email_reply(
                        message_id=orig_msg_id, email_body=summary_text
                    )

                    if result_enrichment["status"] == "success":
                        print("Successfully enriched article")
                    else:
                        print(
                            f"Failed to enrich article: {result_enrichment.get('message', 'Unknown error')}"
                        )

                except Exception as e:
                    print(f"Error enriching article: {e}")

            result.append(reply)

        return result


def is_reply(msg: Message) -> bool:
    return bool(msg.get("In-Reply-To") or msg.get("References"))


def clean_reply_body(body: str) -> str:
    return parser.parse_reply(text=body) or body


def build_analysis_input(thread: dict) -> str:
    lines = [f"Aihe: {thread['subject']}\n", "QUESTIONS:\n"]
    for q in thread["questions"]:
        lines.append(f"{q['position']}. ({q['topic']}) {q['question']}")
    lines.append("\nANSWERS:\n")
    for r in thread["replies"]:
        lines.append(f"-- {r['from']} @ {r['received_at']}")
        lines.append(r["body"].strip())
        lines.append("")
    return "\n".join(lines)


def _extract_body(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset: str = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if isinstance(payload, (bytes, bytearray)):
                    try:
                        return payload.decode(charset, errors="replace")
                    except Exception as e:
                        return f"[Decode error: {e}]"
                if isinstance(payload, str):
                    return payload
    else:
        charset: str = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if isinstance(payload, (bytes, bytearray)):
            try:
                return payload.decode(charset, errors="replace")
            except Exception as e:
                return f"[Decode error: {e}]"
        if isinstance(payload, str):
            return payload
    return ""


if __name__ == "__main__":
    # From email folder "INBOX", read only unseen emails and process them
    read_email_tool(
        folder="INBOX",
        unseen_only=True,
    )
