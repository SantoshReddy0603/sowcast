import json
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

CropName = Literal["ragi", "paddy", "maize", "tur", "groundnut", "tomato"]


class Citation(BaseModel):
    title: str
    publisher: str
    url: str
    locator: str
    statement: str
    number_as_written: str | None = None
    region: str | None = None


class Threshold(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    enabled: bool
    value: float | tuple[int, ...] | str | None
    citation: Citation | None
    reason: str
    unit: str | None = None
    stage: str | None = None
    districts: tuple[str, ...] = ()
    reference_only: bool = False

    @model_validator(mode="after")
    def verified(self) -> "Threshold":
        if self.enabled and (self.value is None or self.citation is None):
            raise ValueError("Enabled thresholds require a value and citation")
        if not self.enabled and self.value is not None:
            raise ValueError("Disabled thresholds must not carry an active value")
        return self


class Catalogue(BaseModel):
    version: str
    crops: dict[CropName, dict[str, Threshold]]
    disabled: Threshold


def load_catalogue() -> Catalogue:
    import yaml  # type: ignore[import-untyped]

    content = files("sowcast.agronomy").joinpath("crops.yaml").read_text(encoding="utf-8")
    return Catalogue.model_validate_json(json.dumps(yaml.safe_load(content)))
