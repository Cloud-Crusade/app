from common.app_factory import createApp

from event.routers import events, health

app = createApp(
    title="Event Service",
    routers=[health.router, events.router],
)
