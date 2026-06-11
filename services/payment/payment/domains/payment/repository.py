from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from payment.domains.payment.model import PaymentHistory


class PaymentRepository:
    """Read 전용 — 본 repo 는 SQS publish 만 담당하고 DB write 는 Lambda repo 가 처리."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def getById(self, payment_history_id: UUID) -> PaymentHistory | None:
        return await self._session.get(PaymentHistory, payment_history_id)

    async def listByOffset(
        self,
        *,
        offset: int,
        limit: int,
        user_id: UUID | None = None,
    ) -> tuple[list[PaymentHistory], int]:
        base = select(PaymentHistory)
        if user_id is not None:
            base = base.where(PaymentHistory.user_id == user_id)
        total = (
            await self._session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        items_stmt = (
            base.order_by(
                PaymentHistory.created_at.desc(),
                PaymentHistory.payment_history_id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        items = list((await self._session.execute(items_stmt)).scalars().all())
        return items, total

    async def existingIds(self, payment_history_ids: list[UUID]) -> set[UUID]:
        if not payment_history_ids:
            return set()
        stmt = select(PaymentHistory.payment_history_id).where(
            PaymentHistory.payment_history_id.in_(payment_history_ids),
        )
        return set((await self._session.execute(stmt)).scalars().all())
