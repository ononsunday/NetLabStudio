import asyncio
async def echo(reader, writer):
    data = await reader.read(4096); writer.write(data); await writer.drain()
    writer.close(); await writer.wait_closed()
async def main():
    server = await asyncio.start_server(echo, "127.0.0.1", 0)
    async with server:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
        writer.write(b"asyncio echo"); await writer.drain()
        print((await asyncio.wait_for(reader.read(4096), 2)).decode())
        writer.close(); await writer.wait_closed()
asyncio.run(main())
