from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.reservation.model import Reservation


class ReservationRepository:
    """Read 전용 — 본 repo 는 SQS publish 만 담당하고 DB write 는 Lambda repo 가 처리."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def getById(self, reservation_id: UUID) -> Reservation | None:
        return await self._session.get(Reservation, reservation_id)

    async def listPaged(
        self,
        *,
        page: int,
        size: int,
        user_id: UUID | None = None,
    ) -> tuple[list[Reservation], int]:
        base = select(Reservation)
        if user_id is not None:
            base = base.where(Reservation.user_id == user_id)
        total = (
            await self._session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        items_stmt = (
            base.order_by(Reservation.created_at.desc(), Reservation.reservation_id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = list((await self._session.execute(items_stmt)).scalars().all())
        return items, total

    async def listByOffset(
        self,
        *,
        offset: int,
        limit: int,
        user_id: UUID | None = None,
    ) -> tuple[list[Reservation], int]:
        base = select(Reservation)
        if user_id is not None:
            base = base.where(Reservation.user_id == user_id)
        total = (
            await self._session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        items_stmt = (
            base.order_by(
                Reservation.created_at.desc(),
                Reservation.reservation_id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        items = list((await self._session.execute(items_stmt)).scalars().all())
        return items, total

    async def existingIds(self, reservation_ids: list[UUID]) -> set[UUID]:
        if not reservation_ids:
            return set()
        stmt = select(Reservation.reservation_id).where(
            Reservation.reservation_id.in_(reservation_ids),
        )
        return set((await self._session.execute(stmt)).scalars().all())
