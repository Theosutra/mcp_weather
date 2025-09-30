import argparse
import asyncio
import json
import os
import re
from typing import Any, Optional

import google.generativeai as genai
from dotenv import load_dotenv

from .open_meteo import get_weather, get_forecast


_INTENT_SYSTEM_PROMPT = (
    "Tu es un extracteur d'intentions météo.\n"
    "Reçois une question utilisateur en français.\n"
    "Retourne STRICTEMENT un JSON avec les clés: city (string), days (integer|optional).\n"
    "Règles:\n"
    "- city: nom de ville détecté (ex: 'Paris').\n"
    "- days: si l'utilisateur parle de 'demain', '3 jours', 'semaine', etc.\n"
    "  - 'aujourd\u2019hui' => days=1\n"
    "  - 'demain' => days=1\n"
    "  - 'X jours' => days=X (1..16)\n"
    "  - sinon omets days.\n"
    "- Ne retourne AUCUN texte hors JSON.\n"
)


def _extract_intent_with_gemini(model: genai.GenerativeModel, question: str) -> dict[str, Any]:
    prompt = _INTENT_SYSTEM_PROMPT + "\nQuestion:\n" + question
    resp = model.generate_content(prompt)
    text = resp.text or "{}"
    # Tente d'isoler le premier bloc JSON dans la réponse
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}


def _summarize_answer(model: genai.GenerativeModel, question: str, raw_data: dict[str, Any]) -> str:
    content = json.dumps(raw_data, ensure_ascii=False)
    resp = model.generate_content(
        "Résume de façon concise et utile la réponse météo en français, à partir du JSON suivant et de la question utilisateur.\n"
        f"Question: {question}\nJSON: {content}"
    )
    return (resp.text or "").strip()


async def handle_question(question: str) -> dict[str, Any]:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY manquant (ou GOOGLE_API_KEY) dans l'environnement / .env")

    genai.configure(api_key=api_key)

    # Modèle configurable (évite l'erreur 404) – valeurs courantes: 
    #  - "gemini-1.5-flash-latest"
    #  - "gemini-1.5-pro-latest"
    #  - "gemini-1.0-pro"
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest")
    model = genai.GenerativeModel(model_name)

    intent = _extract_intent_with_gemini(model, question)
    city: Optional[str] = None
    days: Optional[int] = None

    if isinstance(intent, dict):
        city = (intent.get("city") or None)
        days_val = intent.get("days")
        try:
            days = int(days_val) if days_val is not None else None
        except Exception:
            days = None

    if not city:
        # Fallback très simple si Gemini ne renvoie pas la ville
        # Heuristique: chercher un mot capitalisé (comme Paris, Lyon, etc.)
        m = re.search(r"\b([A-ZÉÈÎÎÂÀ][a-zéèêîïâàç\-]+)\b", question)
        if m:
            city = m.group(1)

    if not city:
        raise ValueError("Ville introuvable dans la question. Spécifie la ville, ex: 'Paris'.")

    if days is None or days <= 1:
        data = await get_weather(city)
    else:
        days = max(1, min(16, int(days)))
        data = await get_forecast(city, days)

    summary = _summarize_answer(model, question, data)
    return {
        "intent": intent,
        "result": data,
        "answer": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Bridge Gemini -> météo (Open-Meteo)")
    parser.add_argument("ask", help="Sous-commande fixe", nargs='?')
    parser.add_argument("--q", required=False, help="Question utilisateur en français")
    args = parser.parse_args()

    question = args.q or "Quel temps fait-il à Paris ?"

    data = asyncio.run(handle_question(question))
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
