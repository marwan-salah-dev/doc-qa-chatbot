"""Who is asking, on the public demo: a visitor id, an admin key and the client's IP.

There is no login. The browser makes a random visitor id (`crypto.randomUUID()`) and sends it as
`X-Visitor-Id` with every request; workspaces and conversations it creates store a SHA-256 of
that id, and only requests carrying the same id reach them. The id is a bearer secret: it is
never stored, logged or echoed. Anyone can mint new ids, so limits are keyed on the client IP
instead, which uvicorn takes from X-Forwarded-For only when the request comes from the compose
network's proxy (step 17), never from a header a client set.

With PUBLIC_DEMO off, `Access.restricted` is False and every route behaves as before.
"""

import hashlib
import ipaddress
import secrets
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.api.deps import AppSettings

VISITOR_HEADER = "X-Visitor-Id"
ADMIN_HEADER = "X-Admin-Key"

MISSING_VISITOR = "Your browser did not send a visitor id. Reload the page and try again."


@dataclass(frozen=True, slots=True)
class Access:
    public: bool
    is_admin: bool
    # SHA-256 of a well-formed visitor id; None when the request had none
    owner_hash: str | None
    # The client IP, or its /64 for IPv6 (one IPv6 client usually holds a whole /64)
    ip_key: str

    @property
    def restricted(self) -> bool:
        """Ownership and the demo's limits apply: the public demo, and not the admin."""
        return self.public and not self.is_admin

    def require_owner(self) -> str | None:
        """The owner hash to store on something new; 400 on the public demo without an id."""
        if not self.public:
            return None
        if self.owner_hash is None and not self.is_admin:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, MISSING_VISITOR)
        return self.owner_hash


def visitor_hash(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        visitor = uuid.UUID(raw)
    except ValueError:
        return None
    return hashlib.sha256(str(visitor).encode()).hexdigest()


def client_key(host: str | None) -> str:
    if not host:
        return "unknown"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host  # e.g. the test client's "testclient"
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def is_admin_key(given: str | None, configured: str) -> bool:
    # An unset key disables admin access rather than matching an empty header
    return bool(configured) and given is not None and secrets.compare_digest(given, configured)


def get_access(request: Request, settings: AppSettings) -> Access:
    return Access(
        public=settings.public_demo,
        is_admin=is_admin_key(
            request.headers.get(ADMIN_HEADER), settings.admin_api_key.get_secret_value()
        ),
        owner_hash=visitor_hash(request.headers.get(VISITOR_HEADER)),
        ip_key=client_key(request.client.host if request.client else None),
    )


AccessDep = Annotated[Access, Depends(get_access)]
