from typing import Annotated
from uuid import UUID

from common.auth import getCurrentUserId
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from event.db import getReaderSession, getWriterSession
from event.domains.event.schema import (
    EventCreate,
    EventPage,
    EventRead,
    EventUpdate,
)
from event.domains.event.service import EventService

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventPage, summary="행사 목록 조회 (페이지네이션)")
async def listEvents(
    session: Annotated[AsyncSession, Depends(getReaderSession)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> EventPage:
    items, total = await EventService(session).listPaged(page=page, size=size)
    return EventPage(
        items=[EventRead.model_validate(e) for e in items],
        total=total,
        page=page,
        size=size,
    )


@router.get(
    "/{event_id}",
    response_model=EventRead,
    summary="행사 단건 조회",
    responses={404: {"description": "행사 없음"}},
)
async def getEvent(
    event_id: UUID,
    session: Annotated[AsyncSession, Depends(getReaderSession)],
) -> EventRead:
    event = await EventService(session).getById(event_id)
    return EventRead.model_validate(event)


@router.post(
    "",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
    summary="행사 등록 (인증 필요)",
    responses={
        401: {"description": "인증 필요"},
        422: {"description": "요청 검증 실패"},
    },
)
async def createEvent(
    payload: EventCreate,
    user_id: Annotated[UUID, Depends(getCurrentUserId)],
    session: Annotated[AsyncSession, Depends(getWriterSession)],
) -> EventRead:
    event = await EventService(session).create(user_id=user_id, payload=payload)
    return EventRead.model_validate(event)


@router.patch(
    "/{event_id}",
    response_model=EventRead,
    summary="행사 수정 (인증 필요)",
    responses={
        401: {"description": "인증 필요"},
        404: {"description": "행사 없음"},
        422: {"description": "요청 검증 실패"},
    },
)
async def updateEvent(
    event_id: UUID,
    payload: EventUpdate,
    _user_id: Annotated[UUID, Depends(getCurrentUserId)],
    session: Annotated[AsyncSession, Depends(getWriterSession)],
) -> EventRead:
    event = await EventService(session).update(event_id=event_id, payload=payload)
    return EventRead.model_validate(event)


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="행사 삭제 (인증 필요)",
    responses={
        401: {"description": "인증 필요"},
        404: {"description": "행사 없음"},
    },
)
async def deleteEvent(
    event_id: UUID,
    _user_id: Annotated[UUID, Depends(getCurrentUserId)],
    session: Annotated[AsyncSession, Depends(getWriterSession)],
) -> None:
    await EventService(session).delete(event_id=event_id)
