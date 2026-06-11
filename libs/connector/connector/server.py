from collections.abc import Callable

from grpc import aio


async def startServer(register: Callable[[aio.Server], None], *, port: int) -> aio.Server:
    """grpc.aio 서버를 생성·기동한다. register 는 servicer 를 서버에 등록하는 콜백."""
    server = aio.server()
    register(server)
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    return server
