import asyncio
import os
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

SERVER = Path(__file__).resolve().parent / "mcp_server.py"


async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env={**os.environ})
    async with Client(params) as client:
        tools = await client.list_tools()
        print("Tools:")
        for tool in tools.tools:
            print(f"  {tool.name}: {tool.description.splitlines()[0]}")

        print("\nnotes_search('how do I make the chat cheaper'):")
        result = await client.call_tool("notes_search", {"query": "how do I make the chat cheaper", "top_k": 2})
        print(result.content[0].text)

        print("\nnotes_search with top_k=50:")
        bad = await client.call_tool("notes_search", {"query": "rag", "top_k": 50})
        print(f"  is_error={bad.is_error}")

        resources = await client.list_resources()
        prompts = await client.list_prompts()
        print("\nResources:", [str(r.uri) for r in resources.resources])
        print("Prompts:", [p.name for p in prompts.prompts])


if __name__ == "__main__":
    asyncio.run(main())
