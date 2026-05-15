import re
from pydantic import BaseModel, Field, field_validator
from typing import Dict, List


class MetricRule(BaseModel):
    name: str
    weights: Dict[str, str]
    weight: float = Field(..., ge=0, le=1)

    @field_validator("weights")
    @classmethod
    def validate_weight_format(cls, v):
        for key, val in v.items():
            if not re.match(r"^[\>\<\=]+\d+(\.\d+)?$", str(val)):
                raise ValueError(
                    f"Invalid weight format '{val}' for key '{key}'. Expected: '>40', '<=30'"
                )
        return v


class SegmentRule(BaseModel):
    segment: str = Field(..., min_length=1)
    metrics: List[MetricRule]

    @field_validator("metrics")
    @classmethod
    def validate_weights_sum(cls, v):
        total = sum(m.weight for m in v)
        if not 0.95 <= total <= 1.05:
            raise ValueError(f"Metrics weights must sum to 1.0, got {total}")
        return v


class StockConfig(BaseModel):
    code: str = Field(..., pattern=r"^\d{6}\.(SZ|SH|BJ)$")
    name: str
    segment: str
    style: str = Field(default="待分类", pattern=r"^(白马股|弹性小票|次新股|待分类)$")
    market_cap_tier: str = Field(default="待分类", pattern=r"^(大盘|中盘|小盘|待分类)$")
