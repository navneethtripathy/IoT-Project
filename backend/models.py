"""
CivicTwin-R — Canonical Data Models

Pydantic models for telemetry messages, zone state, alerts, and experiment results.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SensorStatus(str, enum.Enum):
    VALID = "valid"
    INVALID = "invalid"
    STALE = "stale"
    OFFLINE = "offline"
    SIMULATED = "simulated"


class DataSource(str, enum.Enum):
    # Canonical provenance tags
    WOKWI_SIMULATED = "WOKWI_SIMULATED"
    PYTHON_SIMULATED = "PYTHON_SIMULATED"
    OBSERVED = "OBSERVED"
    REPLAYED_HISTORICAL = "REPLAYED_HISTORICAL"
    DIGITAL_TWIN = "DIGITAL_TWIN"
    IMPUTED = "IMPUTED"

    # Backwards-compatible aliases
    SIMULATOR = "PYTHON_SIMULATED"
    PYTHON_SIMULATOR = "PYTHON_SIMULATED"
    WOKWI = "WOKWI_SIMULATED"
    RECONSTRUCTED = "IMPUTED"
    FORECAST = "DIGITAL_TWIN"
    DIGITAL_TWIN_SIMULATION = "DIGITAL_TWIN"
    PHYSICAL = "OBSERVED"
    PHYSICAL_SENSOR = "OBSERVED"


class AlertLevel(str, enum.Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


class ZoneType(str, enum.Enum):
    PHYSICAL = "physical"
    VIRTUAL = "virtual"


def normalize_data_source(v) -> DataSource:
    """Normalize any string or enum value to the canonical DataSource enum."""
    if isinstance(v, DataSource):
        return v
    if isinstance(v, str):
        normalized = v.strip().upper()
        mapping = {
            "WOKWI_SIMULATED": DataSource.WOKWI_SIMULATED,
            "WOKWI": DataSource.WOKWI_SIMULATED,
            "PYTHON_SIMULATED": DataSource.PYTHON_SIMULATED,
            "PYTHON_SIMULATOR": DataSource.PYTHON_SIMULATED,
            "SIMULATOR": DataSource.PYTHON_SIMULATED,
            "OBSERVED": DataSource.OBSERVED,
            "PHYSICAL": DataSource.OBSERVED,
            "PHYSICAL_SENSOR": DataSource.OBSERVED,
            "REPLAYED_HISTORICAL": DataSource.REPLAYED_HISTORICAL,
            "DIGITAL_TWIN": DataSource.DIGITAL_TWIN,
            "DIGITAL_TWIN_SIMULATION": DataSource.DIGITAL_TWIN,
            "FORECAST": DataSource.DIGITAL_TWIN,
            "IMPUTED": DataSource.IMPUTED,
            "RECONSTRUCTED": DataSource.IMPUTED,
        }
        if normalized in mapping:
            return mapping[normalized]
        try:
            return DataSource(normalized)
        except ValueError:
            pass
    return v


class TelemetryMessage(BaseModel):
    """Canonical telemetry payload from a physical sensor, simulator, or digital twin."""

    schema_version: str = "1.0"
    device_id: str = Field(..., min_length=1, max_length=64)
    zone_id: str = Field(..., min_length=1, max_length=64)
    sequence: int = Field(..., ge=0)
    timestamp: datetime
    distance_cm: Optional[float] = None
    water_level_cm: Optional[float] = None
    water_level_pct: Optional[float] = None
    rain_sensor_raw: Optional[int] = Field(default=None, ge=0, le=4095)
    rain_indicator_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    sensor_status: SensorStatus = SensorStatus.VALID
    source: DataSource = DataSource.PYTHON_SIMULATED
    quality_flags: list[str] = Field(default_factory=list)

    @field_validator("source", mode="before")
    @classmethod
    def _parse_source(cls, v):
        return normalize_data_source(v)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v

    @field_validator("water_level_pct")
    @classmethod
    def _clamp_pct(cls, v):
        if v is not None:
            return max(0.0, min(100.0, v))
        return v


class IngestedTelemetry(TelemetryMessage):
    """Telemetry record with ingestion metadata."""

    ingestion_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    is_duplicate: bool = False
    is_stale: bool = False
    is_reconstructed: bool = False
    reconstruction_method: Optional[str] = None
    scenario_id: Optional[str] = None


class ZoneConfig(BaseModel):
    """Static and default dynamic parameters for a monitoring zone."""

    zone_id: str
    zone_name: str
    zone_type: ZoneType = ZoneType.VIRTUAL
    device_id: Optional[str] = None
    container_height_cm: float = 30.0
    baseline_water_level_cm: float = 5.0
    inflow_rate_cm_per_step: float = 0.0
    drainage_capacity_cm_per_step: float = 0.5
    warn_threshold_pct: float = 70.0
    crit_threshold_pct: float = 85.0
    sensor_interval_sec: float = 5.0
    sensor_reliability: float = 1.0
    network_availability: float = 1.0


class ZoneState(BaseModel):
    """Runtime status for a monitoring zone."""

    zone_id: str
    zone_name: str
    zone_type: ZoneType
    current_water_level_cm: float = 0.0
    current_water_level_pct: float = 0.0
    alert_level: AlertLevel = AlertLevel.NORMAL
    sensor_status: SensorStatus = SensorStatus.VALID
    data_source: DataSource = DataSource.DIGITAL_TWIN
    last_update: Optional[datetime] = None
    is_online: bool = True
    readings_count: int = 0

    @field_validator("data_source", mode="before")
    @classmethod
    def _parse_data_source(cls, v):
        return normalize_data_source(v)


class Alert(BaseModel):
    """Alert event generated upon threshold crossing or clearing."""

    alert_id: str
    zone_id: str
    device_id: Optional[str] = None
    alert_level: AlertLevel
    water_level_pct: float
    threshold_pct: float
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    message: str = ""
    acknowledged: bool = False


class ReconstructionResult(BaseModel):
    """Performance metrics for missing-data reconstruction."""

    scenario_id: str
    method: str
    missing_rate: float
    total_points: int
    missing_points: int
    evaluated_points: int
    mae: float
    rmse: float
    max_error: float


class LatencyResult(BaseModel):
    """Pipeline processing time metrics."""

    scenario_id: str
    messages_sent: int
    messages_received: int
    delivery_rate: float
    mean_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float
    max_latency_ms: float


class ExperimentSummary(BaseModel):
    """Summary of experiment execution across scenarios."""

    experiment_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    scenario_ids: list[str] = Field(default_factory=list)
    reconstruction_results: list[ReconstructionResult] = Field(default_factory=list)
    latency_results: list[LatencyResult] = Field(default_factory=list)
    notes: str = ""
