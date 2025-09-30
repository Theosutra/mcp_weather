import os
import json
import asyncio
import uuid
from typing import Any, Dict, Optional
from datetime import datetime

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import StreamingResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route

from .open_meteo import get_weather as ow_get_weather, get_forecast as ow_get_forecast

# Auth
AUTH_TOKEN = (os.getenv("MCP_AUTH_TOKEN", "") or "").strip().strip('"')

def _check_auth(req: Request) -> bool:
    if not AUTH_TOKEN:
        return True
    auth = req.headers.get("authorization") or req.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return False
    received = auth.split(" ", 1)[1].strip().strip('"')
    return received == AUTH_TOKEN

# Définition des outils MCP
TOOLS = [
    {
        "name": "get_weather",
        "description": "Météo actuelle pour une ville",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Nom de la ville"}
            },
            "required": ["city"],
        }
    },
    {
        "name": "get_forecast",
        "description": "Prévisions quotidiennes pour une ville",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Nom de la ville"},
                "days": {"type": "integer", "minimum": 1, "maximum": 16, "description": "Nombre de jours"}
            },
            "required": ["city", "days"],
        }
    },
]

async def execute_tool(name: str, arguments: Dict[str, Any]) -> str:
    """Exécute un outil et retourne le résultat en JSON"""
    try:
        if name == "get_weather":
            city = str(arguments.get("city", ""))
            if not city:
                return json.dumps({"error": "city parameter required"})
            data = await ow_get_weather(city)
            return json.dumps(data, ensure_ascii=False)
        elif name == "get_forecast":
            city = str(arguments.get("city", ""))
            days = int(arguments.get("days", 3))
            if not city:
                return json.dumps({"error": "city parameter required"})
            data = await ow_get_forecast(city, days)
            return json.dumps(data, ensure_ascii=False)
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def create_jsonrpc_response(result: Any, request_id: Optional[Any] = None) -> Dict:
    """Crée une réponse JSON-RPC 2.0"""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result
    }

def create_jsonrpc_error(code: int, message: str, request_id: Optional[Any] = None) -> Dict:
    """Crée une erreur JSON-RPC 2.0"""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message
        }
    }

async def handle_jsonrpc_message(message: Dict) -> Dict:
    """Traite un message JSON-RPC MCP"""
    method = message.get("method")
    params = message.get("params", {})
    msg_id = message.get("id")

    # Initialize
    if method == "initialize":
        return create_jsonrpc_response({
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "mcp-weather",
                "version": "1.0.0"
            }
        }, msg_id)

    # Initialized (notification, pas de réponse)
    elif method == "initialized":
        return None

    # List tools
    elif method == "tools/list":
        return create_jsonrpc_response({
            "tools": TOOLS
        }, msg_id)

    # Call tool
    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        
        result_text = await execute_tool(tool_name, tool_args)
        
        return create_jsonrpc_response({
            "content": [
                {
                    "type": "text",
                    "text": result_text
                }
            ]
        }, msg_id)

    # Méthode non supportée
    else:
        return create_jsonrpc_error(-32601, f"Method not found: {method}", msg_id)

# Endpoint SSE principal
async def mcp_sse_endpoint(request: Request):
    if not _check_auth(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    
    async def event_generator():
        try:
            # Lire le corps de la requête (POST avec messages JSON-RPC)
            if request.method == "POST":
                body = await request.body()
                if body:
                    try:
                        message = json.loads(body.decode('utf-8'))
                        response = await handle_jsonrpc_message(message)
                        
                        if response:
                            # Format SSE
                            event_data = f"data: {json.dumps(response)}\n\n"
                            yield event_data.encode('utf-8')
                    except json.JSONDecodeError:
                        error = create_jsonrpc_error(-32700, "Parse error")
                        yield f"data: {json.dumps(error)}\n\n".encode('utf-8')
            
            # Garder la connexion ouverte pour d'autres messages
            # (dans une vraie implémentation SSE bidirectionnelle, 
            # on attendrait d'autres messages via un mécanisme de queue)
            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            error = create_jsonrpc_error(-32603, f"Internal error: {str(e)}")
            yield f"data: {json.dumps(error)}\n\n".encode('utf-8')
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

# Endpoint HTTP standard pour messages JSON-RPC
async def mcp_jsonrpc_endpoint(request: Request):
    if not _check_auth(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    
    try:
        body = await request.json()
        response = await handle_jsonrpc_message(body)
        
        if response:
            return JSONResponse(response)
        else:
            # Notification sans réponse
            return JSONResponse({"ok": True}, status_code=204)
    
    except json.JSONDecodeError:
        return JSONResponse(create_jsonrpc_error(-32700, "Parse error"), status_code=400)
    except Exception as e:
        return JSONResponse(create_jsonrpc_error(-32603, f"Internal error: {str(e)}"), status_code=500)

# Endpoint d'information (GET simple)
async def mcp_info_endpoint(request: Request):
    if not _check_auth(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    
    return JSONResponse({
        "server": "mcp-weather",
        "version": "1.0.0",
        "protocol": "MCP",
        "protocolVersion": "2024-11-05",
        "endpoints": {
            "sse": "/mcp/sse",
            "jsonrpc": "/mcp",
        },
        "tools": [tool["name"] for tool in TOOLS],
        "capabilities": ["tools"]
    })

# Health check
async def health_endpoint(request: Request):
    return JSONResponse({
        "ok": True,
        "server": "mcp-weather",
        "timestamp": datetime.utcnow().isoformat()
    })

routes = [
    Route("/mcp", mcp_jsonrpc_endpoint, methods=["POST"]),
    Route("/mcp", mcp_info_endpoint, methods=["GET"]),
    Route("/mcp/sse", mcp_sse_endpoint, methods=["GET", "POST"]),
    Route("/health", health_endpoint, methods=["GET"]),
]

app = Starlette(debug=False, routes=routes)