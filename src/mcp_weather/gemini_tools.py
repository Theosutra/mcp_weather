import asyncio
import json
import os
import re
from typing import Any, Dict, List
from datetime import date, timedelta

import google.generativeai as genai
from dotenv import load_dotenv

from .open_meteo import get_weather, get_forecast


def _init_model() -> genai.GenerativeModel:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY manquant (ou GOOGLE_API_KEY)")

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest")

    tool_spec = {
        "function_declarations": [
            {
                "name": "get_weather",
                "description": "Météo actuelle pour une ville",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"city": {"type": "STRING"}},
                    "required": ["city"],
                },
            },
            {
                "name": "get_forecast",
                "description": "Prévisions quotidiennes (1..16) pour une ville",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "city": {"type": "STRING"},
                        "days": {"type": "INTEGER"},
                    },
                    "required": ["city", "days"],
                },
            },
        ]
    }

    return genai.GenerativeModel(model_name, tools=[tool_spec])


def _title_city(name: str | None) -> str | None:
    if not name:
        return None
    return name.strip().title()


def _infer_city_from_text(text: str) -> str | None:
    # 1) Préposition + Ville (insensible à la casse)
    preposition_pattern = r"(?:\bà\b|\ba\b|\bsur\b|\bpour\b|\ben\b|\bvers\b)\s+([A-Za-zÉÈÎÂÀÀÂÇÉÈÊËÎÏÔÖÙÛÜŸ\-]+)"
    m = re.search(preposition_pattern, text, flags=re.IGNORECASE)
    if m:
        return _title_city(m.group(1))

    # 2) Dernier nom propre pertinent
    stop = {"Donne", "Moi", "Salut", "Bonjour", "Quel", "Quoi", "Temps", "Fait", "Au", "Pour", "Les", "Prochains", "Jours", "Demain", "Aujourd", "Hui", "La", "Semaine", "Pro"}
    candidates = re.findall(r"\b([A-ZÉÈÎÂÀ][a-zàâçéèêëîïôöùûüÿ\-]+)\b", text)
    candidates = [c for c in candidates if c not in stop and len(c) > 2]
    if candidates:
        return _title_city(candidates[-1])
    return None


def _days_to_cover_next_monday_to_sunday(today: date) -> int:
    # Prochaine semaine = lundi (prochain) à dimanche (inclus)
    weekday = today.weekday()  # lundi=0..dimanche=6
    days_until_next_monday = (7 - weekday) % 7
    if days_until_next_monday == 0:
        days_until_next_monday = 7  # si on est lundi, viser le lundi suivant
    total = days_until_next_monday + 7
    return min(total, 16)


def _infer_days_from_text(text: str) -> int | None:
    if re.search(r"\bdemain\b", text, flags=re.IGNORECASE):
        return 1
    # "semaine pro" / "semaine prochaine" -> couvrir du lundi au dimanche prochains
    if re.search(r"semaine\s+(pro|prochaine)", text, flags=re.IGNORECASE) or re.search(r"\bsemaine\b", text, flags=re.IGNORECASE):
        return _days_to_cover_next_monday_to_sunday(date.today())
    m = re.search(r"(\d{1,2})\s*jours?", text, flags=re.IGNORECASE)
    if m:
        try:
            val = int(m.group(1))
            if 1 <= val <= 16:
                return val
        except Exception:
            pass
    return None


def _normalize_arguments(raw_fc: Any) -> Dict[str, Any]:
    args: Dict[str, Any] = {}
    if hasattr(raw_fc, "args") and isinstance(raw_fc.args, dict):
        args = dict(raw_fc.args)
    elif hasattr(raw_fc, "arguments") and isinstance(raw_fc.arguments, str):
        try:
            parsed = json.loads(raw_fc.arguments)
            if isinstance(parsed, dict):
                args = parsed
        except Exception:
            args = {}
    elif isinstance(raw_fc, dict):
        cand_args = raw_fc.get("arguments")
        if isinstance(cand_args, dict):
            args = cand_args
        elif isinstance(cand_args, str):
            try:
                parsed = json.loads(cand_args)
                if isinstance(parsed, dict):
                    args = parsed
            except Exception:
                pass
    return args


def _run_tool_call(name: str, arguments: Dict[str, Any], user_text: str) -> Dict[str, Any]:
    if name == "get_weather":
        city = arguments.get("city") or _infer_city_from_text(user_text)
        city = _title_city(city)
        if not city:
            raise KeyError("city manquant pour get_weather")
        return asyncio.run(get_weather(str(city)))
    if name == "get_forecast":
        city = arguments.get("city") or _infer_city_from_text(user_text)
        city = _title_city(city)
        days_val = arguments.get("days")
        days = None
        try:
            days = int(days_val) if days_val is not None else None
        except Exception:
            days = None
        if days is None:
            days = _infer_days_from_text(user_text) or 3
        if not city:
            raise KeyError("city manquant pour get_forecast")
        return asyncio.run(get_forecast(str(city), int(days)))
    raise ValueError(f"Tool inconnu: {name}")


def _summarize_answer(model: genai.GenerativeModel, question: str, tool_result: Dict[str, Any]) -> str:
    content = json.dumps(tool_result, ensure_ascii=False)
    resp = model.generate_content(
        "Résume en français de façon concise et utile, à partir de la question et du JSON.\n"
        f"Question: {question}\nJSON: {content}"
    )
    return (resp.text or "").strip()


def chat_with_tools(question: str) -> str:
    model = _init_model()

    # 1) Tour initial
    msg = model.generate_content(question)

    # 2) Inspecter s’il y a un appel de fonction
    function_calls: List[Dict[str, Any]] = []
    try:
        for cand in (msg.candidates or []):
            parts = getattr(cand.content, "parts", None) or []
            for part in parts:
                fc = getattr(part, "function_call", None)
                if fc:
                    args = _normalize_arguments(fc)
                    function_calls.append({"name": fc.name, "arguments": args})
    except Exception:
        pass

    if not function_calls:
        # Fallback: si la question ressemble à une intention météo, on appelle l’outil même sans function_call
        city = _infer_city_from_text(question)
        days = _infer_days_from_text(question)
        if city:
            if days is None or days <= 1:
                tool_result = asyncio.run(get_weather(city))
            else:
                tool_result = asyncio.run(get_forecast(city, days))
            return _summarize_answer(model, question, tool_result)
        # Sinon, réponse directe du modèle
        return msg.text or ""

    # 3) Exécuter le premier tool demandé
    call = function_calls[0]
    tool_result = _run_tool_call(call["name"], call["arguments"], question)

    # 4) Résumer le résultat
    return _summarize_answer(model, question, tool_result)
