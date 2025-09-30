# MCP Weather (Open-Meteo)

Mini-projet: exposer la météo via Model Context Protocol (MCP) en Python, sans clé API, en s'appuyant sur Open‑Meteo.

## Prérequis
- Docker / Docker Compose (déploiement recommandé)
- Optionnel (local): Python 3.10+

## Démarrage rapide (Docker)
```bash
# À la racine du projet
# Définir un token d’accès (recommandé)
$env:MCP_AUTH_TOKEN="change_me_long"      # PowerShell
# export MCP_AUTH_TOKEN="change_me_long"  # bash

docker compose up -d --build
# Test (si exposé en local)
curl -H "Authorization: Bearer change_me_long" http://localhost:8085/mcp
```

Placez ensuite un reverse proxy (Nginx) devant le conteneur pour le domaine public.

### Nginx (exemple)
```
server {
    listen 80;
    server_name mcp.ia-datasulting.fr;

    location /mcp {
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization $http_authorization;
        proxy_http_version 1.1;
        proxy_set_header Connection keep-alive;
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_pass http://127.0.0.1:8085;
    }
}
```
- Générez un certificat TLS (ex: certbot) et basculez en HTTPS.

## Utilisation locale (sans Docker)
```bash
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
python -m src.mcp_weather.mcp_server  # STDIO (Claude/Cursor)
# ou
uvicorn src.mcp_weather.mcp_sse_app:app --host 127.0.0.1 --port 8085  # SSE (HTTP)
```

## Outils
- `get_weather(city)` → météo actuelle
- `get_forecast(city, days)` → prévisions quotidiennes (1..16)

## Notes
- Endpoint `/mcp` renvoie une info de santé basique. Pour l’intégration GPT via MCP/SSE, ajoutez l’URL et le header `Authorization: Bearer <TOKEN>` dans la configuration du GPT (voir doc OpenAI MCP).
