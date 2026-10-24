"""The address of the client behind a reverse proxy.

Behind a proxy every request arrives from the proxy's address, so a per-address rate limit would
treat all users as one. `X-Forwarded-For` carries the real address, but a client can put anything
it likes at the front of that header. Each trusted proxy appends the address it received the
connection from, so the entries added by *our* proxies are at the end of the list: with N trusted
proxies the client's address is the Nth from the right. Anything to its left is untrusted input
and is ignored.
"""

from fastapi import Request


def client_ip(request: Request, trusted_hops: int) -> str:
    """The client's address, trusting only the last `trusted_hops` entries of the header.

    With `trusted_hops=0` (the default, for running without a proxy) the header is ignored
    entirely. If the header is missing or shorter than expected, which means the request did not
    come through the proxy we expect, the connecting address is used.
    """
    peer = request.client.host if request.client else "unknown"
    if trusted_hops <= 0:
        return peer
    entries = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",")]
    entries = [entry for entry in entries if entry]
    if len(entries) >= trusted_hops:
        return entries[-trusted_hops]
    return peer
