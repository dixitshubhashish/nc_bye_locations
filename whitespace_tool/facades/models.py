"""Facade module re-exporting dataclass models from whitespace_tool.common.models."""

from whitespace_tool.common.models import LocationRecord, ZipDemographics, utc_now_iso

__all__ = ["LocationRecord", "ZipDemographics", "utc_now_iso"]

