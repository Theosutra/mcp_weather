# MCP Weather (Open-Meteo)

Mini-projet: exposer la météo via Model Context Protocol (MCP) en Python, sans clé API, en s'appuyant sur Open‑Meteo.

## Prérequis
- Python 3.10+
- Windows PowerShell (fourni) ou un shell équivalent

## Installation
```bash
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

## Utilisation CLI
Deux fonctions principales:
- `get_weather(city)` → météo actuelle d'une ville
- `get_forecast(city, days)` → prévisions quotidiennes

```bash
# Météo actuelle
python -m src.mcp_weather.cli weather --city "Paris"

# Prévisions sur 3 jours
python -m src.mcp_weather.cli forecast --city "Paris" --days 3
```

## Démarrer le serveur MCP
Le serveur expose les outils MCP `get_weather` et `get_forecast`.

```bash
python -m src.mcp_weather.mcp_server
```

Le serveur communique en STDIO (conforme MCP). Utilisez un client MCP compatible pour s'y connecter (ex: IDE/agent compatible MCP).

## Bridge Gemini (optionnel)
Permet de poser une question en français; Gemini extrait l’intention (ville, jours) puis appelle la météo.

1) Mettre la clé dans `.env`:
```
GEMINI_API_KEY=xxxxxxxxxxxxxxxx
```
2) Lancer le bridge:
```bash
python -m src.mcp_weather.gemini_bridge --q "Quel temps fait-il à Paris demain ?"
```
3) Sortie: JSON contenant `intent`, `result` (brut) et `answer` (résumé en français).

Note: Le bridge appelle directement les fonctions Python `get_weather`/`get_forecast`. Si vous préférez forcer un appel via MCP, utilisez un client MCP (Claude, Cursor) déjà configuré.

## Notes techniques
- API de géocodage: `https://geocoding-api.open-meteo.com/v1/search`
- API météo: `https://api.open-meteo.com/v1/forecast`
- Libs: `httpx`, `pydantic`, `mcp`


