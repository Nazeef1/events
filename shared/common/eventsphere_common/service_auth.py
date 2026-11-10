"""
Zero-trust authentication for service-to-service calls.

Internal routes (/internal/*) are never exposed by the API gateway, but
being unreachable from the browser is not the same as being safe: anything
that can reach a service on the network (another container, a compromised
pod) could otherwise call "confirm this booking" or "issue this refund".
So no caller is trusted because of where it sits. Every internal request
must prove who sent it:

  * Each caller -> target pair has its own secret, held only by those two
    services: INTERNAL_KEY_<CALLER>_TO_<TARGET>, e.g. INTERNAL_KEY_PAYMENT_TO_BOOKING.
    A compromised service can therefore not impersonate a different caller.
  * The caller sends a short-lived signed token in the X-Service-Token header.
    It names the caller (iss) and the intended target (aud) and expires after
    TOKEN_TTL_SECONDS, so a leaked token is useless elsewhere and soon useless.
  * Each internal route lists exactly which callers it accepts (least privilege).
  * A missing key fails closed: the call is refused, never waved through.

User JWTs (the Authorization header) are unaffected; this is a separate layer.
"""
from __future__ import annotations

import os
import time
import uuid

from fastapi import Header, HTTPException, status
from jose import JWTError, jwt

HEADER = "X-Service-Token"
TOKEN_TTL_SECONDS = 60
_ALGORITHM = "HS256"


def _key_name(caller: str, target: str) -> str:
    return f"INTERNAL_KEY_{caller.upper()}_TO_{target.upper()}"


def _key(caller: str, target: str) -> str | None:
    return os.environ.get(_key_name(caller, target)) or None


def service_headers(caller: str, target: str) -> dict[str, str]:
    """Headers for an outgoing internal call from `caller` to `target`."""
    key = _key(caller, target)
    if not key:
        raise RuntimeError(f"{_key_name(caller, target)} is not set, so {caller} cannot call {target}")
    now = int(time.time())
    claims = {"iss": caller, "aud": target, "iat": now, "exp": now + TOKEN_TTL_SECONDS, "jti": str(uuid.uuid4())}
    return {HEADER: jwt.encode(claims, key, algorithm=_ALGORITHM)}


def require_service(target: str, *allowed_callers: str):
    """
    FastAPI dependency for an internal route on service `target` that only
    `allowed_callers` may call. With no allowed callers the route refuses everyone.
    Returns the verified caller name.
    """

    def _verify(x_service_token: str | None = Header(default=None, alias=HEADER)) -> str:
        if not x_service_token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Service token required")
        try:
            caller = jwt.get_unverified_claims(x_service_token).get("iss")
        except JWTError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed service token")
        if caller not in allowed_callers:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This service is not allowed to call this route")
        key = _key(caller, target)
        if not key:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This service is not allowed to call this route")
        try:
            # Checks the signature with the pair's own key, the audience, the issuer and expiry.
            jwt.decode(x_service_token, key, algorithms=[_ALGORITHM], audience=target, issuer=caller)
        except JWTError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired service token")
        return caller

    return _verify
