"""Caller identity.

Authentication is not implemented yet (milestone M7). Until then every request is attributed to
one local owner. Replace `get_owner_id` with a real dependency; ownership checks elsewhere already
filter by the value it returns.
"""

LOCAL_OWNER_ID = "local-user"


def get_owner_id() -> str:
    return LOCAL_OWNER_ID
