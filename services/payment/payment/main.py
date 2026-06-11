from common.app_factory import createApp

from payment.routers import health, payments

app = createApp(
    title="Payment Service",
    routers=[health.router, payments.router],
)
