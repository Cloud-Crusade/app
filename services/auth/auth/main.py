from common.app_factory import createApp

from auth.routers import auth, health, users

app = createApp(
    title="Auth Service",
    routers=[health.router, auth.router, users.router],
)
