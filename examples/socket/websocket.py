import asyncio
from websockets.asyncio.server import serve
from websockets.asyncio.client import connect
async def echo(websocket):
    async for message in websocket: await websocket.send(message)
async def main():
    async with serve(echo, "127.0.0.1", 0) as server:
        async with connect("ws://127.0.0.1:%d/" % server.sockets[0].getsockname()[1], proxy=None) as client:
            await client.send("WebSocket frame"); print(await client.recv())
asyncio.run(main())
