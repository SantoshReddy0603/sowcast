import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from sowcast.agronomy.water_balance import District
from sowcast.sources.models import Location

Point = tuple[float, float]
Ring = tuple[Point, ...]
Polygon = tuple[Ring, ...]
DATA = Path(__file__).parent / "data"
ALIASES: dict[str, District] = {
    "Bangalore Rural": "Bengaluru Rural",
    "Kolar": "Kolar",
    "Tumkur": "Tumakuru",
    "Chikkaballapura": "Chikkaballapura",
    "Ramanagara": "Ramanagara",
}


class DistrictResult(BaseModel):
    api_version: Literal["1.0"] = "1.0"
    location: Location
    status: Literal["matched", "ambiguous", "unavailable"]
    district: str | None = None
    supported_district: District | None = None
    source: str = "geoBoundaries gbOpen India ADM2"
    source_url: str = "https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/"
    attribution: str = "geoBoundaries; Pathways Data Pvt. Ltd. and lgdirectory.gov.in"
    licence_url: str = "https://opendatacommons.org/licenses/odbl/1-0/"
    boundary_year: int = 2021
    limitation: str = (
        "Approximate lookup using simplified 2021 district boundaries. "
        "Names and boundaries may have changed; confirm near a boundary."
    )


@dataclass(frozen=True)
class Boundary:
    name: str
    polygons: tuple[Polygon, ...]
    bounds: tuple[float, float, float, float]


@lru_cache(maxsize=1)
def boundaries() -> tuple[Boundary, ...]:
    payload: dict[str, Any] = json.loads((DATA / "india-districts.json").read_text("utf-8"))
    result = []
    for feature in payload["features"]:
        geometry = feature["geometry"]
        coordinates = geometry["coordinates"]
        raw_polygons: list[list[list[list[float]]]] = (
            [coordinates] if geometry["type"] == "Polygon" else coordinates
        )
        polygons = tuple(
            tuple(tuple((point[0], point[1]) for point in ring) for ring in polygon)
            for polygon in raw_polygons
        )
        points = [point for polygon in polygons for point in polygon[0]]
        result.append(
            Boundary(
                feature["properties"]["shapeName"],
                polygons,
                (
                    min(p[0] for p in points),
                    min(p[1] for p in points),
                    max(p[0] for p in points),
                    max(p[1] for p in points),
                ),
            )
        )
    return tuple(result)


def ring_position(point: Point, ring: Ring) -> Literal["inside", "outside", "boundary"]:
    x, y = point
    inside = False
    for start, end in zip(ring, (*ring[1:], ring[0]), strict=True):
        x1, y1 = start
        x2, y2 = end
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if (
            abs(cross) <= 1e-10
            and min(x1, x2) - 1e-10 <= x <= max(x1, x2) + 1e-10
            and min(y1, y2) - 1e-10 <= y <= max(y1, y2) + 1e-10
        ):
            return "boundary"
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return "inside" if inside else "outside"


def polygon_position(point: Point, polygon: Polygon) -> Literal["inside", "outside", "boundary"]:
    exterior = ring_position(point, polygon[0])
    if exterior != "inside":
        return exterior
    for hole in polygon[1:]:
        position = ring_position(point, hole)
        if position == "boundary":
            return "boundary"
        if position == "inside":
            return "outside"
    return "inside"


def identify_district(location: Location) -> DistrictResult:
    point = (location.longitude, location.latitude)
    matches: set[str] = set()
    on_boundary = False
    for boundary in boundaries():
        west, south, east, north = boundary.bounds
        if not (west <= point[0] <= east and south <= point[1] <= north):
            continue
        for polygon in boundary.polygons:
            position = polygon_position(point, polygon)
            if position != "outside":
                matches.add(boundary.name)
                on_boundary |= position == "boundary"
    if len(matches) != 1 or on_boundary:
        return DistrictResult(location=location, status="ambiguous" if matches else "unavailable")
    name = matches.pop()
    supported = ALIASES.get(name)
    return DistrictResult(
        location=location,
        status="matched",
        district=supported or name,
        supported_district=supported,
    )
