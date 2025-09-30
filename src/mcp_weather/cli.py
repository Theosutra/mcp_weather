import argparse
import asyncio
import json
from typing import Any

from .open_meteo import get_weather, get_forecast


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI météo (Open-Meteo)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("weather", help="Météo actuelle")
    p1.add_argument("--city", required=True, help="Ville, ex: Paris")

    p2 = sub.add_parser("forecast", help="Prévisions quotidiennes")
    p2.add_argument("--city", required=True, help="Ville, ex: Paris")
    p2.add_argument("--days", type=int, default=3, help="Nombre de jours (1..16)")

    args = parser.parse_args()

    if args.cmd == "weather":
        data = asyncio.run(get_weather(args.city))
        _print_json(data)
    elif args.cmd == "forecast":
        data = asyncio.run(get_forecast(args.city, args.days))
        _print_json(data)
    else:
        parser.error("Commande inconnue")


if __name__ == "__main__":
    main()


