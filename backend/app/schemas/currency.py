"""Currency reference schemas."""

from pydantic import BaseModel, ConfigDict, Field


class CurrencyResponse(BaseModel):
    """One currency as the interface needs it: how to write it and how to round it."""

    model_config = ConfigDict(from_attributes=True)

    code: str = Field(..., min_length=3, max_length=4)
    symbol: str
    decimals: int = Field(..., ge=0, le=4)
    rounding_step: int = Field(..., ge=1)
    countries: list[str] = Field(default_factory=list)
