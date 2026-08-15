"""User dashboard routes — profile, credits."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, hash_password
from app.models.models import User
from app.schemas.schemas import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url
    if payload.password:
        current_user.hashed_password = hash_password(payload.password)

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/me/dashboard")
async def dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lightweight dashboard summary for the home page."""
    songs = (
        await db.execute(select(User).where(User.id == current_user.id))
    ).scalar_one()
    return {
        "user": UserRead.model_validate(current_user).model_dump(mode="json"),
        "credits_remaining": current_user.credits,
        "songs_count": len(current_user.songs),
    }
