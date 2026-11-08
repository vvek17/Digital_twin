"""Server-held, expiring admin grants. No Streamlit dependency."""

import hashlib
import hmac
import secrets
import time


_GRANTS = {}


def verify_password(candidate, configured):
    return (isinstance(configured, str) and bool(configured.strip())
            and isinstance(candidate, str)
            and hmac.compare_digest(candidate.encode(), configured.encode()))


class AdminAuthority:
    def __init__(self, secret_provider, session_id):
        self.secret_provider = secret_provider
        self.session_id = session_id

    @property
    def configured(self):
        value = self.secret_provider()
        return isinstance(value, str) and bool(value.strip())

    def login(self, password):
        configured = self.secret_provider()
        if not verify_password(password, configured):
            raise PermissionError("Incorrect password or admin access is not configured")
        now = time.time()
        for token, grant in list(_GRANTS.items()):
            if grant[2] <= now:
                _GRANTS.pop(token, None)
        token = secrets.token_urlsafe(32)
        _GRANTS[token] = (self.session_id, hashlib.sha256(configured.encode()).digest(), now + 8 * 3600)
        return token

    def require(self, token):
        configured = self.secret_provider()
        grant = _GRANTS.get(token) if isinstance(token, str) else None
        if (not self.configured or grant is None or grant[0] != self.session_id
                or grant[2] <= time.time()
                or not hmac.compare_digest(grant[1], hashlib.sha256(configured.encode()).digest())):
            raise PermissionError("Admin login is required. Please log in again.")

    def logout(self, token):
        if isinstance(token, str):
            _GRANTS.pop(token, None)
