#!/usr/bin/env python3
import asyncio
from mcpify import mcpify
import example_tools

server = mcpify(
    example_tools,
    getattr,
    setattr,
    server_name=""
)

async def main():
    await server.run()

if __name__ == "__main__":
    asyncio.run(main()) 