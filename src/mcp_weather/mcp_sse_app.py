import os
import json
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from mcp.server import Server
from mcp.types import Tool, TextContent
from .open_meteo import get_weather as ow_get_weather, get_forecast as ow_get_forecast

# Même définition de serveur/outils que le serveur STDIO
server = Server("mcp-weather")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
	return [
		Tool(
			name="get_weather",
			description="Météo actuelle pour une ville",
			inputSchema={
				"type": "object",
				"properties": {"city": {"type": "string", "description": "Nom de la ville"}},
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
					"days": {"type": "integer", "minimum": 1, "maximum": 16},
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


# Auth simple par Bearer
AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "")

def _check_auth(req: Request) -> bool:
	if not AUTH_TOKEN:
		return True  # si pas de token configuré, pas de protection (déconseillé en prod)
	auth = req.headers.get("authorization") or req.headers.get("Authorization")
	if not auth or not auth.lower().startswith("bearer "):
		return False
	return auth.split(" ", 1)[1] == AUTH_TOKEN


# Endpoint MCP SSE minimaliste — proxy la requête/flux vers le serveur
# Note: En pratique, utiliser un utilitaire du SDK MCP pour SSE si dispo; ici, on répond aux init simples.
async def mcp_endpoint(request: Request):
	if not _check_auth(request):
		return PlainTextResponse("Unauthorized", status_code=401)
	# Pour une intégration complète SSE (stream), on utiliserait un endpoint EventSourceResponse
	# et le protocole complet. Ici, on expose une route d’info simple pour vérification.
	return JSONResponse({
		"server": "mcp-weather",
		"tools": ["get_weather", "get_forecast"],
	})


routes = [
	Route("/mcp", mcp_endpoint, methods=["GET"]),
]

app = Starlette(debug=False, routes=routes)
