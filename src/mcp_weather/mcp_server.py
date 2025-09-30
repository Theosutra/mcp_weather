import asyncio
import json
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .open_meteo import get_weather as ow_get_weather, get_forecast as ow_get_forecast


server = Server("mcp-weather")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_weather",
            description="Météo actuelle pour une ville",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "Nom de la ville"}
                },
                "required": ["city"],
            }
        ),
        Tool(
            name="get_forecast",
            description="Prévisions quotidiennes pour une ville",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 16}
                },
                "required": ["city", "days"],
            }
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "get_weather":
        city = str(arguments.get("city"))
        data = await ow_get_weather(city)
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]
    if name == "get_forecast":
        city = str(arguments.get("city"))
        days = int(arguments.get("days", 3))
        data = await ow_get_forecast(city, days)
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]
    raise ValueError(f"Outil inconnu: {name}")


async def main() -> None:
    print("[mcp-weather] serveur démarré (STDIO)", file=sys.stderr, flush=True)
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())