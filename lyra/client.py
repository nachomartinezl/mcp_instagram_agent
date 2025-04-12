import asyncio
import os
import json
from typing import Optional
from contextlib import AsyncExitStack

from dotenv import load_dotenv
from google import genai
from google.genai import types

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()


class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = "gemini-2.0-flash"

    async def connect_to_server(self, server_script_path: str):
        is_python = server_script_path.endswith(".py")
        is_js = server_script_path.endswith(".js")
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(command=command, args=[server_script_path], env=None)

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        await self.session.initialize()

        tools = await self.session.list_tools()
        print("\n🔌 Connected to server with tools:", [t.name for t in tools.tools])

    async def _gemini_decide_tool(self, query: str, tools: list) -> dict:
        tool_info = json.dumps([
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in tools
        ], indent=2)

        prompt = f"""
You are a tool-using agent. Based on this tool list:

{tool_info}

Decide which tool to use based on the user's query below. Return a JSON object ONLY, no explanation:

{{
  "tool": "<tool_name>",
  "args": {{ ... }}
}}

User query: {query}
"""

        contents = [types.Content(parts=[types.Part(text=prompt)])]
        config = types.GenerateContentConfig(response_mime_type="text/plain")

        response_text = ""
        for chunk in self.gemini.models.generate_content_stream(
            model=self.model,
            contents=contents,
            config=config
        ):
            if chunk.text:
                response_text += chunk.text

        print("\n🔮 Gemini Raw Response:\n", response_text.strip())
        return self._parse_json_response(response_text)

    def _parse_json_response(self, raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join([line for line in raw.splitlines() if not line.strip().startswith("```")])
        try:
            return json.loads(raw)
        except Exception as e:
            raise ValueError(f"Could not parse Gemini output as JSON:\n\n{raw}") from e

    async def process_query(self, query: str) -> str:
        if not self.session:
            raise RuntimeError("MCP session is not initialized")

        tool_list = await self.session.list_tools()
        parsed = await self._gemini_decide_tool(query, tool_list.tools)

        tool = parsed["tool"]
        args = parsed["args"]

        try:
            print(f"\n⚙️ Calling tool `{tool}` with args: {args}")
            result = await self.session.call_tool(tool, args)
            return f"[✅ Called `{tool}`]\n\n{result.content}"
        except Exception as e:
            return f"[❌ Failed to call tool]\n{e}\n\n🧪 Parsed: {parsed}"

    async def chat_loop(self):
        print("\n✨ MCP + Gemini client started. Type your query or `quit` to exit.\n")
        while True:
            try:
                query = input("🧠 You: ").strip()
                if query.lower() in {"quit", "exit"}:
                    break
                response = await self.process_query(query)
                print("\n🤖 Gemini:\n", response)
            except Exception as e:
                print(f"\n🚨 Error: {e}")

    async def shutdown(self):
        await self.exit_stack.aclose()


async def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python client.py path/to/server.py")
        return

    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
