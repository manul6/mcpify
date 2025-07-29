#!/usr/bin/env python3
import asyncio
from mcp.server.stdio import stdio_server
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions
from mcpify import mcpify

def add(a: int, b: int) -> int:
    """add two numbers"""
    return a + b

def greet(name: str) -> str:
    """greet someone"""
    return f"hello {name}!"

def multiply(x: int, y: int) -> int:
    """multiply two numbers"""
    return x * y

server = mcpify([add, greet, multiply, getattr])

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcpify-minimal",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            )
        )

if __name__ == "__main__":
    asyncio.run(main()) 