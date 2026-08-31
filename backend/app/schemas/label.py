"""Bounded, identity-independent label presentation options."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LabelField = Literal[
    "nozzle", "bed", "drying", "abrasiveness", "diameter", "density", "weight", "chamber"
]


class LabelOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width_mm: float = Field(default=50, ge=8, le=220, allow_inf_nan=False)
    height_mm: float = Field(default=30, ge=8, le=220, allow_inf_nan=False)
    kind: Literal["full", "classic"] = "full"
    color_mode: Literal["mono", "color"] = "mono"
    dpi: Literal[203, 300, 600] = 203
    locale: Literal["ru", "en", "zh"] = "ru"
    attribution: Literal["full", "mark", "none"] = "full"
    qr_mark: bool = False
    brand_logo: bool = True
    border: bool = False
    fields: list[LabelField] = Field(
        default_factory=lambda: ["nozzle", "bed", "drying", "abrasiveness", "diameter", "density"],
        max_length=6,
    )
    comment: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def validate_content(self) -> "LabelOptions":
        if len(set(self.fields)) != len(self.fields):
            raise ValueError("Label fields must be unique")
        if self.kind == "classic" and self.width_mm != self.height_mm:
            raise ValueError("Classic QR media must be square")
        if self.comment and not self.supports_comment:
            raise ValueError("Manufacturer comments require larger media")
        return self

    @property
    def supports_comment(self) -> bool:
        return (
            self.kind == "full"
            and min(self.width_mm, self.height_mm) >= 50
            and self.width_mm * self.height_mm >= 6000
        )


class LabelExportOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: LabelOptions = Field(default_factory=LabelOptions)
    format: Literal["svg", "png", "pdf"] = "svg"
    media: Literal["single", "a4", "letter"] = "single"
    copies: int = Field(default=1, ge=1, le=50)
    start_position: int = Field(default=1, ge=1, le=500)
    page_margin_mm: float = Field(default=5, ge=0, le=25, allow_inf_nan=False)
    gap_mm: float = Field(default=2, ge=0, le=10, allow_inf_nan=False)
    crop_marks: bool = False

    @model_validator(mode="after")
    def validate_media(self) -> "LabelExportOptions":
        if self.media == "single" and (self.copies != 1 or self.start_position != 1):
            raise ValueError("Single media contains exactly one label")
        if self.media == "single" and self.crop_marks:
            raise ValueError("Crop marks require sheet media")
        return self
