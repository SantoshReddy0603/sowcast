import hashlib
import json

import httpx
import pytest

from sowcast.api.app import create_app
from sowcast.geography.districts import DATA, boundaries, identify_district, polygon_position
from sowcast.sources.models import Location


@pytest.mark.parametrize(
    "latitude,longitude,expected",
    [
        (13.14, 78.13, "Kolar"),
        (13.29, 77.54, "Bengaluru Rural"),
        (13.34, 77.1, "Tumakuru"),
        (13.43, 77.73, "Chikkaballapura"),
        (12.72, 77.28, "Ramanagara"),
    ],
)
def test_supported_districts_from_published_boundaries(latitude, longitude, expected):
    result = identify_district(Location(latitude=latitude, longitude=longitude))
    assert result.status == "matched"
    assert result.district == result.supported_district == expected


@pytest.mark.parametrize(
    "latitude,longitude,expected",
    [
        (12.97, 77.59, "Bangalore"),
        (12.3, 76.65, "Mysore"),
    ],
)
def test_other_districts_do_not_enable_pilot_guidance(latitude, longitude, expected):
    result = identify_district(Location(latitude=latitude, longitude=longitude))
    assert result.status == "matched" and result.district == expected
    assert result.supported_district is None


def test_ocean_remains_unidentified():
    result = identify_district(Location(latitude=0, longitude=0))
    assert result.status == "unavailable"
    assert result.district is None and result.supported_district is None


def test_boundary_pin_requires_manual_confirmation():
    longitude, latitude = boundaries()[0].polygons[0][0][0]
    result = identify_district(Location(latitude=latitude, longitude=longitude))
    assert result.status == "ambiguous"
    assert result.district is None and result.supported_district is None


def test_polygon_holes_edges_and_vertices_are_not_silently_assigned():
    exterior = ((0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (0.0, 0.0))
    hole = ((1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0), (1.0, 1.0))
    polygon = (exterior, hole)
    assert polygon_position((3.0, 3.0), polygon) == "inside"
    assert polygon_position((1.5, 1.5), polygon) == "outside"
    assert polygon_position((0.0, 2.0), polygon) == "boundary"
    assert polygon_position((0.0, 0.0), polygon) == "boundary"
    assert polygon_position((1.0, 1.5), polygon) == "boundary"
    assert polygon_position((5.0, 5.0), polygon) == "outside"


def test_packaged_dataset_matches_recorded_provenance():
    payload = (DATA / "india-districts.json").read_bytes()
    provenance = json.loads((DATA / "provenance.json").read_text())
    assert hashlib.sha256(payload).hexdigest() == provenance["packaged_sha256"]
    assert len(json.loads(payload)["features"]) == provenance["actual_feature_count"] == 735
    assert provenance["boundaryYearRepresented"] == "2021"


@pytest.mark.asyncio
async def test_district_api_is_local_and_validates_coordinates():
    def unexpected_request(request):
        pytest.fail("District identification must not call an upstream service")

    app = create_app(httpx.MockTransport(unexpected_request))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/v1/places/district?latitude=13.14&longitude=78.13")
            assert response.status_code == 200
            body = response.json()
            assert body["district"] == "Kolar" and body["status"] == "matched"
            assert body["boundary_year"] == 2021 and body["source_url"]
            assert (
                await client.get("/v1/places/district?latitude=91&longitude=78")
            ).status_code == 422
            assert (
                await client.get("/v1/places/district?latitude=nan&longitude=78")
            ).status_code == 422
            assert (await client.get("/v1/places/district?latitude=13")).status_code == 422
            health = (await client.get("/health/sources")).json()["sources"]
            assert all(source["request_count"] == 0 for source in health.values())
