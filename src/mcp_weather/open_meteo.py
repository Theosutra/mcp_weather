from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class Coordinates(BaseModel):
    latitude: float
    longitude: float
    name: str = Field(default="")
    country_code: Optional[str] = None
    timezone: Optional[str] = None


class CurrentWeather(BaseModel):
    temperature_c: float = Field(alias="temperature_2m")
    relative_humidity: Optional[float] = Field(default=None, alias="relative_humidity_2m")
    apparent_temperature_c: Optional[float] = Field(default=None, alias="apparent_temperature")
    weather_code: Optional[int] = Field(default=None, alias="weather_code")
    wind_speed_kmh: Optional[float] = Field(default=None, alias="wind_speed_10m")
    precipitation_mm: Optional[float] = Field(default=None, alias="precipitation")
    description: Optional[str] = None

    class Config:
        populate_by_name = True


class DailyForecastItem(BaseModel):
    date: str
    temp_min_c: Optional[float] = None
    temp_max_c: Optional[float] = None
    precipitation_sum_mm: Optional[float] = None
    wind_speed_max_kmh: Optional[float] = None
    weather_code: Optional[int] = None
    description: Optional[str] = None


class ForecastResult(BaseModel):
    city: str
    coordinates: Coordinates
    days: int
    daily: List[DailyForecastItem]


WEATHER_CODE_FR: Dict[int, str] = {
    0: "Ciel dégagé",
    1: "Principalement clair",
    2: "Partiellement nuageux",
    3: "Couvert",
    45: "Brouillard",
    48: "Brouillard givrant",
    51: "Bruine légère",
    53: "Bruine modérée",
    55: "Bruine dense",
    56: "Bruine verglaçante légère",
    57: "Bruine verglaçante dense",
    61: "Pluie faible",
    63: "Pluie modérée",
    65: "Pluie forte",
    66: "Pluie verglaçante légère",
    67: "Pluie verglaçante forte",
    71: "Chute de neige faible",
    73: "Chute de neige modérée",
    75: "Chute de neige forte",
    77: "Grains de neige",
    80: "Averses faibles",
    81: "Averses modérées",
    82: "Averses fortes",
    85: "Averses de neige faibles",
    86: "Averses de neige fortes",
    95: "Orage",
    96: "Orage avec grésil léger",
    99: "Orage avec grésil fort",
}


def _get_weather_description(code: Optional[int]) -> Optional[str]:
    if code is None:
        return None
    return WEATHER_CODE_FR.get(code, f"Code météo {code}")


async def _geocode_city(client: httpx.AsyncClient, city: str) -> Coordinates:
    params = {
        "name": city,
        "count": 1,
        "language": "fr",
        "format": "json",
    }
    resp = await client.get(GEOCODING_URL, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or []
    if not results:
        raise ValueError(f"Ville introuvable: {city}")
    r0 = results[0]
    return Coordinates(
        latitude=r0["latitude"],
        longitude=r0["longitude"],
        name=r0.get("name", city),
        country_code=r0.get("country_code"),
        timezone=r0.get("timezone"),
    )


async def _fetch_current_weather(client: httpx.AsyncClient, coords: Coordinates) -> CurrentWeather:
    params = {
        "latitude": coords.latitude,
        "longitude": coords.longitude,
        "current": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "weather_code",
            "wind_speed_10m",
            "precipitation",
        ]),
        "timezone": "auto",
    }
    resp = await client.get(FORECAST_URL, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    current_raw = (payload.get("current") or {})
    current = CurrentWeather.model_validate(current_raw, from_attributes=False)
    current.description = _get_weather_description(current.weather_code)
    return current


async def _fetch_daily_forecast(
    client: httpx.AsyncClient,
    coords: Coordinates,
    days: int,
) -> ForecastResult:
    days = max(1, min(16, int(days)))
    params = {
        "latitude": coords.latitude,
        "longitude": coords.longitude,
        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "wind_speed_10m_max",
        ]),
        "forecast_days": days,
        "timezone": "auto",
    }
    resp = await client.get(FORECAST_URL, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()

    daily = payload.get("daily") or {}
    dates: List[str] = daily.get("time") or []
    wcodes: List[Optional[int]] = daily.get("weather_code") or [None] * len(dates)
    tmax: List[Optional[float]] = daily.get("temperature_2m_max") or [None] * len(dates)
    tmin: List[Optional[float]] = daily.get("temperature_2m_min") or [None] * len(dates)
    ps: List[Optional[float]] = daily.get("precipitation_sum") or [None] * len(dates)
    wmax: List[Optional[float]] = daily.get("wind_speed_10m_max") or [None] * len(dates)

    items: List[DailyForecastItem] = []
    for i, d in enumerate(dates):
        code = (wcodes[i] if i < len(wcodes) else None)
        items.append(
            DailyForecastItem(
                date=d,
                temp_min_c=(tmin[i] if i < len(tmin) else None),
                temp_max_c=(tmax[i] if i < len(tmax) else None),
                precipitation_sum_mm=(ps[i] if i < len(ps) else None),
                wind_speed_max_kmh=(wmax[i] if i < len(wmax) else None),
                weather_code=code,
                description=_get_weather_description(code),
            )
        )

    return ForecastResult(
        city=coords.name,
        coordinates=coords,
        days=len(items),
        daily=items,
    )


async def get_weather(city: str) -> Dict[str, Any]:
    """Renvoie la météo actuelle pour une ville.

    Retourne un dictionnaire simple, facilement sérialisable.
    """
    async with httpx.AsyncClient() as client:
        coords = await _geocode_city(client, city)
        current = await _fetch_current_weather(client, coords)
        return {
            "city": coords.name,
            "coordinates": coords.model_dump(),
            "current": current.model_dump(by_alias=True),
        }


async def get_forecast(city: str, days: int) -> Dict[str, Any]:
    """Renvoie les prévisions quotidiennes sur N jours (1..16)."""
    async with httpx.AsyncClient() as client:
        coords = await _geocode_city(client, city)
        forecast = await _fetch_daily_forecast(client, coords, days)
        return forecast.model_dump()


