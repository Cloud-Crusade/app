import json
from typing import Any

import aioboto3
import structlog

from common.settings import settings

logger = structlog.get_logger()


class SqsPublisher:
    """SQS 메시지 발행을 담당. 본 repo 는 발행만 하고, 소비/처리는 Lambda repo 의 책임."""

    def __init__(self, queue_url: str) -> None:
        self._queue_url = queue_url
        self._session = aioboto3.Session(region_name=settings.aws_region)

    def _clientKwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"region_name": settings.aws_region}
        if settings.aws_endpoint_url:
            kwargs["endpoint_url"] = settings.aws_endpoint_url
        return kwargs

    async def publish(
        self,
        *,
        message: dict[str, Any],
        group_id: str | None = None,
        dedup_id: str | None = None,
    ) -> str:
        body = json.dumps(message, default=str)
        async with self._session.client("sqs", **self._clientKwargs()) as sqs:
            params: dict[str, Any] = {"QueueUrl": self._queue_url, "MessageBody": body}
            if group_id is not None:
                params["MessageGroupId"] = group_id
            if dedup_id is not None:
                params["MessageDeduplicationId"] = dedup_id
            response = await sqs.send_message(**params)
        message_id = response["MessageId"]
        logger.info(
            "sqs_published",
            queue=self._queue_url,
            message_id=message_id,
            action=message.get("action"),
        )
        return message_id


_reservationPublisher: SqsPublisher | None = None


def getReservationSqsPublisher() -> SqsPublisher:
    global _reservationPublisher
    if _reservationPublisher is None:
        _reservationPublisher = SqsPublisher(settings.sqs_reservation_queue_url)
    return _reservationPublisher
