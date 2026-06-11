from common.app_factory import createApp
from config.settings import settings

from reservation.routers import captcha, health, queue, reservations

routers = [health.router, reservations.router, captcha.router]
# 대기열은 운영에서 API Gateway → Lambda 가 처리 — dev/test 에서만 in-memory 스텁 등록
if settings.env in {"development", "test"}:
    routers.append(queue.router)

app = createApp(title="Reservation Service", routers=routers)
