import asyncio
from insta.server import InstagramServer

async def main():
    server = InstagramServer()
    await server.init()
    await server.snapshot_page_tree()
    await server.close()

if __name__ == "__main__":
    asyncio.run(main())
