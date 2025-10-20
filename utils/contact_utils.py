import os
import random
from typing import List, Optional


def _parse_env_list(value: Optional[str]) -> List[str]:
    """Parse a comma-separated .env list into a clean list of strings.

    Handles optional quotes and extra spaces.
    """
    if not value:
        return []

    # Strip surrounding quotes if any
    v = value.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1]

    parts = [p.strip() for p in v.split(',')]
    return [p for p in parts if p]


def get_random_phone_from_env(fallback: Optional[str] = None) -> Optional[str]:
    """Return a random phone number from CONTACT_PHONE_LIST.

    Fallback order:
    1) CONTACT_PHONE_LIST (random)
    2) CONTACT_PERSON_PHONE
    3) WHERE_TO_CALL
    4) provided fallback argument
    """
    phone_list = _parse_env_list(os.getenv("CONTACT_PHONE_LIST"))
    if phone_list:
        return random.choice(phone_list)

    # Fallbacks if list is empty
    single = os.getenv("CONTACT_PERSON_PHONE") or os.getenv("WHERE_TO_CALL")
    return single or fallback


def get_random_email_from_env(fallback: Optional[str] = None) -> Optional[str]:
    """Return a random email from CONTACT_EMAIL_LIST with fallbacks.

    Fallback order:
    1) CONTACT_EMAIL_LIST (random)
    2) CONTACT_PERSON_EMAIL
    3) provided fallback argument
    """
    email_list = _parse_env_list(os.getenv("CONTACT_EMAIL_LIST"))
    if email_list:
        return random.choice(email_list)

    single = os.getenv("CONTACT_PERSON_EMAIL")
    return single or fallback
