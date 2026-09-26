"""Auth router: register + login, and the get_current_user dependency.

Design decisions
----------------
- Passwords: bcrypt (default cost 12) — industry standard; login failures
  are uniform 401s that never reveal whether the username or the password
  was wrong.
- Tokens: opaque random strings (secrets.token_urlsafe(32), 256 bits of
  entropy), stored as sha256 hash only (see AuthToken in models.py) — a
  database leak exposes no usable credentials. No expiry (deliberate
  scope choice): revocation = delete the row; trade-off in the README.
- OAuth2PasswordBearer(tokenUrl="/auth/login") makes /docs render an
  Authorize button — it sends username/password as a form, exactly the
  shape OAuth2PasswordRequestForm parses (hence python-multipart).
"""

import hashlib
import secrets

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuthToken, User
from app.schemas import Token, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

# tokenUrl tells /docs' Authorize button where to POST username/password.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_CRED_HDR = {"WWW-Authenticate": "Bearer"}


def _hash_token(raw: str) -> str:
    """sha256 hex — fast lookup, irreversible (fine: 256-bit input entropy)."""
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("/register", response_model=UserRead, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    if db.scalar(select(User).where(User.username == payload.username)) is not None:
        raise HTTPException(status_code=409, detail="Username already taken")

    # bcrypt works on bytes; gensalt() embeds cost + salt in the output.
    password_hash = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    user = User(username=payload.username, password_hash=password_hash)

    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Race: name claimed between our check and the commit — the UNIQUE
        # constraint is the real guarantee; this handler is the friendly path.
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already taken") from None
    return user


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.username == form.username))
    # Guard-or-evaluate: short-circuit skips bcrypt when the user doesn't
    # exist. Responses are identical either way — uniform 401.
    if user is None or not bcrypt.checkpw(form.password.encode(), user.password_hash.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers=_CRED_HDR,
        )

    raw = secrets.token_urlsafe(32)  # shown to the client exactly once
    db.add(AuthToken(user_id=user.id, token_hash=_hash_token(raw)))
    db.commit()
    return Token(access_token=raw)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Resolve the bearer token to a User; 401 on any miss.

    This is the AUTHENTICATION gate (who are you). AUTHORIZATION (is this
    row yours?) stays in the routers' ownership-scoped queries.
    """
    auth_token = db.scalar(select(AuthToken).where(AuthToken.token_hash == _hash_token(token)))
    if auth_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token", headers=_CRED_HDR
        )
    user = db.get(User, auth_token.user_id)
    if user is None:
        # CASCADE deletes tokens with users, so this is near-impossible —
        # but refusing costs nothing.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token", headers=_CRED_HDR
        )
    return user
