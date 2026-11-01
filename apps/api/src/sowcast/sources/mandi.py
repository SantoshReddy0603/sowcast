from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from sowcast.sources.base import SourceClientBase, metadata
from sowcast.sources.models import SourceError, SourceEvidence, SourceHealth
from sowcast.sources.transport import QueryValue, SourceTransport

URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"


class MandiPrice(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    state: str
    district: str
    market: str
    commodity: str
    variety: str | None = None
    arrival_date: str
    min_price: float | None
    max_price: float | None
    modal_price: float | None

    @field_validator("min_price", "max_price", "modal_price", mode="before")
    @classmethod
    def missing_price(cls, value: Any) -> Any:
        return None if value in ("", "NA", "N/A", None) else value


class MandiEvidence(SourceEvidence):
    state: str
    district: str
    commodity: str
    records: tuple[MandiPrice, ...]
    price_unit: str | None = None
    limitation: str = (
        "Returned page only, not necessarily latest records. Arrival dates are source text. "
        "Price unit and authenticated response schema require live verification."
    )


class MandiClient(SourceClientBase):
    def __init__(self, transport: SourceTransport, api_key: str | None) -> None:
        super().__init__(transport)
        self.api_key = api_key
        if not api_key:
            self.transport.health = SourceHealth(
                status="unconfigured", error_code="missing_api_key"
            )

    async def fetch(self, district: str, commodity: str) -> MandiEvidence:
        if not self.api_key:
            raise SourceError(
                "missing_api_key",
                "AGMARKNET_API_KEY is not configured",
                False,
                self.transport.source,
            )
        if not district.strip() or not commodity.strip():
            raise ValueError("District and commodity are required")
        params: dict[str, QueryValue] = {
            "api-key": self.api_key,
            "format": "json",
            "limit": 10,
            "offset": 0,
            "filters[state]": "Karnataka",
            "filters[district]": district,
            "filters[commodity]": commodity,
        }

        def parse(payload: dict[str, Any]) -> MandiEvidence:
            records = tuple(MandiPrice.model_validate(row) for row in payload["records"])
            if any(
                row.state != "Karnataka"
                or row.district.casefold() != district.casefold()
                or row.commodity.casefold() != commodity.casefold()
                for row in records
            ):
                raise ValueError("Unexpected market filter results")
            return MandiEvidence(
                **metadata(
                    "agmarknet",
                    URL,
                    params,
                    "Directorate of Marketing and Inspection, via data.gov.in",
                    "https://www.data.gov.in/",
                    None,
                    "Selected record fields; API credential omitted from provenance.",
                ),
                state="Karnataka",
                district=district,
                commodity=commodity,
                records=records,
                data_status="partial" if records else "empty",
                missing_reasons=(
                    "Authenticated record schema and price unit are not yet verified.",
                ),
            )

        return await self.request(URL, params, parse)
