from typing import Any

from sowcast.sources.base import SourceClientBase, metadata
from sowcast.sources.models import Location, SourceEvidence
from sowcast.sources.transport import QueryValue

URL = "https://geocoding-api.open-meteo.com/v1/search"


class Place(Location):
    id: int
    name: str
    country_code: str
    admin1: str | None = None
    admin2: str | None = None
    timezone: str | None = None


class GeocodingEvidence(SourceEvidence):
    query: str
    language: str
    places: tuple[Place, ...]


class GeocodingClient(SourceClientBase):
    async def fetch(self, name: str, language: str = "en") -> GeocodingEvidence:
        if not 2 <= len(name.strip()) <= 120 or language not in (
            "en",
            "hi",
            "kn",
            "te",
            "ta",
            "mr",
        ):
            raise ValueError("Provide a place name and supported language")
        params: dict[str, QueryValue] = {
            "name": name.strip(),
            "count": 5,
            "language": language,
            "format": "json",
            "countryCode": "IN",
        }

        def parse(payload: dict[str, Any]) -> GeocodingEvidence:
            places = tuple(Place.model_validate(row) for row in payload.get("results", []))
            if any(place.country_code != "IN" for place in places):
                raise ValueError("Unexpected country in geocoding results")
            return GeocodingEvidence(
                **metadata(
                    "open_meteo_geocoding",
                    URL,
                    params,
                    "Location data by GeoNames, via Open-Meteo.com",
                    "https://open-meteo.com/",
                    "https://creativecommons.org/licenses/by/4.0/",
                    "Selected place fields.",
                ),
                query=name.strip(),
                language=language,
                places=places,
                data_status="complete" if places else "empty",
                missing_reasons=() if places else ("No matching places returned.",),
            )

        return await self.request(URL, params, parse)
