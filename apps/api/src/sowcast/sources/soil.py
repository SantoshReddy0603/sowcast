from typing import Any

from pydantic import BaseModel, ConfigDict

from sowcast.sources.base import SourceClientBase, metadata
from sowcast.sources.models import Location, SourceEvidence
from sowcast.sources.transport import QueryValue

URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPERTIES = ("clay", "sand", "silt", "phh2o", "soc")


class SoilProperty(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    name: str
    depth: str
    mapped_value: float | None
    mapped_unit: str
    conversion_factor: float
    value: float | None
    unit: str


class SoilEvidence(SourceEvidence):
    location: Location
    properties: tuple[SoilProperty, ...]
    limitation: str = "SoilGrids model estimates for the top 5 cm, not a plot soil test."


class SoilClient(SourceClientBase):
    async def fetch(self, location: Location) -> SoilEvidence:
        params: dict[str, QueryValue] = {
            "lat": location.latitude,
            "lon": location.longitude,
            "property": list(PROPERTIES),
            "depth": "0-5cm",
            "value": "mean",
        }

        def parse(payload: dict[str, Any]) -> SoilEvidence:
            properties: list[SoilProperty] = []
            for layer in payload["properties"]["layers"]:
                name = layer["name"]
                if name not in PROPERTIES:
                    raise ValueError("Unexpected soil property")
                unit = layer["unit_measure"]
                factor = float(unit["d_factor"])
                if factor <= 0:
                    raise ValueError("Invalid soil scale factor")
                depths = layer["depths"]
                if len(depths) != 1 or depths[0]["label"] != "0-5cm":
                    raise ValueError("Unexpected soil depth")
                raw = depths[0]["values"]["mean"]
                properties.append(
                    SoilProperty(
                        name=name,
                        depth=depths[0]["label"],
                        mapped_value=raw,
                        mapped_unit=unit["mapped_units"],
                        conversion_factor=factor,
                        value=None if raw is None else raw / factor,
                        unit=unit["target_units"],
                    )
                )
            if len(properties) != len(PROPERTIES) or {p.name for p in properties} != set(
                PROPERTIES
            ):
                raise ValueError("Missing or duplicate soil properties")
            count = sum(prop.value is not None for prop in properties)
            return SoilEvidence(
                **metadata(
                    "soilgrids",
                    URL,
                    params,
                    "ISRIC — World Soil Information, SoilGrids 2.0",
                    "https://www.isric.org/explore/soilgrids",
                    "https://creativecommons.org/licenses/by/4.0/",
                    "Selected mean topsoil properties; divided by returned d_factor.",
                ),
                location=location,
                properties=tuple(properties),
                data_status="complete"
                if count == len(PROPERTIES)
                else "partial"
                if count
                else "empty",
                missing_reasons=()
                if count == len(PROPERTIES)
                else ("SoilGrids returned null property means.",),
            )

        return await self.request(URL, params, parse)
