"""대기열 순번 조회 — dev/로컬 전용 in-memory 스텁.

운영에서는 API Gateway 가 `/queue/{event_id}` 를 ticketing Lambda 로 라우팅하며 이 라우트는
호출되지 않는다(대기열 단일 출처는 cc/lambda 의 ticketing). 본 모듈은 로컬에서 web 의 대기
게이트를 동작시키기 위한 최소 구현으로, 프로세스 메모리 dict 로 (event_id, user_id) 별 잔여
폴링 수를 관리한다 — 분산·영속 보장이 없으므로 dev/test 한정으로만 등록한다(main 에서 게이팅).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps import getCurrentUser
from app.domains.user.model import User

router = APIRouter(prefix="/queue", tags=["queue"])

# 이 횟수만큼 WAITING 응답 후 COMPLETED 로 전환 (web 폴링 2s 기준 약 6s)
_ADMIT_AFTER_POLLS = 3
# (event_id, user_id) -> 남은 대기 폴링 수
_queue_state: dict[tuple[str, str], int] = {}


class QueueData(BaseModel):
    token: str | None = None
    position: int | None = None


class QueueStatusResponse(BaseModel):
    code: str
    message: str
    data: QueueData | None = None


@router.get(
    "/{event_id}",
    response_model=QueueStatusResponse,
    summary="대기열 순번 조회 (dev 전용 in-memory 스텁)",
    responses={401: {"description": "인증 필요"}},
)
async def getQueueStatus(
    event_id: str,
    user: Annotated[User, Depends(getCurrentUser)],
) -> QueueStatusResponse:
    key = (event_id, str(user.user_id))
    remaining = _queue_state.get(key, _ADMIT_AFTER_POLLS)

    # 입장 완료 — 예매 진입 토큰 발급(로컬은 authorizer 검증이 없어 불투명 문자열로 충분)
    if remaining <= 0:
        _queue_state[key] = 0
        return QueueStatusResponse(
            code="COMPLETED",
            message="입장 순번이 되었습니다.",
            data=QueueData(token=f"dev-queue.{event_id}.{user.user_id}"),
        )

    # 대기 — 폴링마다 순번 감소
    _queue_state[key] = remaining - 1
    return QueueStatusResponse(
        code="WAITING",
        message="현재 대기열",
        data=QueueData(position=remaining),
    )
