from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.passwords import hash_password
from app.db.session import DatabaseUnavailable
from app.models.identity import Role, SecurityEvent, User, UserRole
from app.schemas.auth import RegistrationRequest


def register_user(session: Session, request: RegistrationRequest) -> None:
    # Hash all valid requests, including duplicates; never replace an existing account's hash.
    encoded = hash_password(request.password.get_secret_value())
    with session.begin():
        viewer_id = session.scalar(select(Role.id).where(Role.code == "viewer"))
        if viewer_id is None:
            raise DatabaseUnavailable("Identity migration is required")
        user_id = session.scalar(
            insert(User)
            .values(
                id=uuid4(),
                email=str(request.email),
                display_name=request.display_name,
                password_hash=encoded,
                status="pending",
            )
            .on_conflict_do_nothing(index_elements=[User.email])
            .returning(User.id)
        )
        if user_id is not None:
            session.add(UserRole(user_id=user_id, role_id=viewer_id))
            session.add(SecurityEvent(subject_user_id=user_id, event="account_registered"))
