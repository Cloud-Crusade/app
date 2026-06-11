from grpc import aio

# 멀티 pod 분산: round_robin LB 로 채널이 모든 백엔드 pod 서브채널을 유지(풀링)한다.
# target 은 headless service + dns:/// 형식(dns:///event-grpc:50051)이어야 모든 pod IP 가
# 해소되어 분산이 동작한다. keepalive 로 idle 연결의 LB drop 을 방지한다.
_CHANNEL_OPTIONS = [
    ("grpc.lb_policy_name", "round_robin"),
    ("grpc.keepalive_time_ms", 30000),
    ("grpc.keepalive_timeout_ms", 10000),
    ("grpc.keepalive_permit_without_calls", 1),
]


def createChannel(target: str) -> aio.Channel:
    return aio.insecure_channel(target, options=_CHANNEL_OPTIONS)


class GrpcChannelPool:
    """서비스 간 gRPC 채널 풀 — 멀티 pod 분산 + 채널 재사용.

    round_robin 채널 1개가 이미 모든 백엔드 pod 의 서브채널을 풀링하므로 size=1 로 충분하다.
    처리량이 더 필요하면 size 를 늘려 RPC 를 채널 단위로 라운드로빈한다. 채널은 프로세스 수명
    동안 재사용하고(요청마다 생성 금지), 종료 시 close 한다.
    """

    def __init__(self, target: str, *, size: int = 1) -> None:
        if size < 1:
            raise ValueError("pool size must be >= 1")
        self._channels = [createChannel(target) for _ in range(size)]
        self._cursor = 0

    def channel(self) -> aio.Channel:
        channel = self._channels[self._cursor % len(self._channels)]
        self._cursor += 1
        return channel

    async def close(self) -> None:
        for channel in self._channels:
            await channel.close()
