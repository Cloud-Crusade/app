from typing import Annotated

from fastapi import APIRouter, Depends

from app.common.deps import getCurrentUser
from app.domains.user.model import User
from app.domains.user.schema import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def getMe(user: Annotated[User, Depends(getCurrentUser)]) -> UserRead:
    return UserRead.model_validate(user)
