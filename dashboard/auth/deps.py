"""
FastAPI dependencies for authentication and authorization.
"""
import getpass
import os
from typing import Optional
from fastapi import Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from dashboard.config import AUTH_ENABLED, SESSION_COOKIE_NAME
from dashboard.auth.session import UserSession, session_store
from dashboard.auth.bridge import get_local_user_info, verify_sudo_password

# Session handed to every request while AUTH_ENABLED is false. It is built once
# per process and kept out of session_store so a logout request cannot delete it.
AUTO_SESSION_ID = "begonia-local-session"
_auto_session: Optional[UserSession] = None


def get_auto_session() -> UserSession:
    """
    Return the always-on session used when authentication is disabled.

    It carries the identity of the user the unit already runs as (the dashboard
    executes its privileged work through that same account), so it grants no
    privilege that the process did not already hold: it only removes the login
    gate. Keep AUTH_ENABLED=1 for any deployment reachable outside this host's
    own tailnet.
    """
    global _auto_session
    if _auto_session is not None:
        return _auto_session

    username = getpass.getuser()
    try:
        info = get_local_user_info(username)
    except Exception:
        info = {
            "uid": os.getuid(),
            "gid": os.getgid(),
            "groups": [],
            "home": os.path.expanduser("~"),
            "shell": "",
        }

    _auto_session = UserSession(
        session_id=AUTO_SESSION_ID,
        username=username,
        uid=info.get("uid", os.getuid()),
        gid=info.get("gid", os.getgid()),
        home=info.get("home", ""),
        shell=info.get("shell", ""),
        groups=info.get("groups", []),
        is_admin=True,
    )
    return _auto_session


async def get_current_session(request: Request) -> Optional[UserSession]:
    """
    Extract session from signed cookie, if valid and active.
    Attaches session to request.state for template rendering.
    """
    if not AUTH_ENABLED:
        session = get_auto_session()
        request.state.session = session
        return session

    # Check if already resolved in request state
    if hasattr(request.state, "session") and request.state.session is not None:
        return request.state.session

    token = request.cookies.get(SESSION_COOKIE_NAME)
    sid = None
    if token:
        sid = session_store.verify_token(token)
        if not sid and token in session_store._sessions:
            sid = token

    # Fallback for localhost if local session is seeded
    if not sid:
        client_host = request.client.host if request.client else ""
        if client_host in ("127.0.0.1", "localhost", "::1"):
            if "dev-session-active" in session_store._sessions:
                sid = "dev-session-active"

    if not sid:
        request.state.session = None
        return None

    session = await session_store.get(sid)
    request.state.session = session
    return session


async def require_session(
    request: Request,
    session: Optional[UserSession] = Depends(get_current_session),
) -> UserSession:
    """
    Ensure caller is authenticated.
    Redirects HTML page requests to /login, raises 401 for API calls.
    """
    if session is not None:
        return session

    # Determine if request expects an HTML response or JSON
    accept = request.headers.get("accept", "")
    is_html_request = "text/html" in accept or not request.url.path.startswith("/api")

    if is_html_request:
        next_path = request.url.path
        if request.url.query:
            next_path += f"?{request.url.query}"
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": f"/login?next={next_path}"},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please sign in.",
    )


async def require_admin(
    request: Request,
    session: UserSession = Depends(require_session),
) -> UserSession:
    """
    Ensure authenticated user has elevated administrative privileges.
    Accepts on-the-fly password validation via 'X-Admin-Password' header if not already elevated.
    """
    if session.is_elevated():
        return session

    # Check for direct password elevation in header
    admin_pwd = request.headers.get("X-Admin-Password")
    if admin_pwd:
        from dashboard.auth.bridge import verify_sudo_password
        valid, err = await verify_sudo_password(admin_pwd)
        if valid:
            session.elevate()
            return session

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Administrative access required. Please enter password to elevate.",
    )
