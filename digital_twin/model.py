"""
CivicTwin-R — Digital Twin Zone Model

Simplified discrete-time mass-balance water-level simulation across monitoring zones.
Models net level changes as: inflow minus drainage, clamped to container geometry.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("civictwin.twin.model")

BASE_DT_SEC = 5.0


@dataclass
class ZoneReading:
    """Output telemetry of a single simulation step for one zone."""

    zone_id: str
    step: int
    timestamp: datetime
    true_level_cm: float
    true_level_pct: float
    observed_level_cm: Optional[float]
    observed_level_pct: Optional[float]
    sensor_ok: bool
    network_ok: bool
    sensor_status: str
    alert_level: str
    quality_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "step": self.step,
            "timestamp": self.timestamp.isoformat(),
            "true_level_cm": self.true_level_cm,
            "true_level_pct": self.true_level_pct,
            "observed_level_cm": self.observed_level_cm,
            "observed_level_pct": self.observed_level_pct,
            "sensor_ok": self.sensor_ok,
            "network_ok": self.network_ok,
            "sensor_status": self.sensor_status,
            "alert_level": self.alert_level,
            "quality_flags": self.quality_flags,
        }


@dataclass
class ZoneModel:
    """Represents a discrete-time water level catchment zone."""

    zone_id: str
    zone_name: str
    subbasin: str = "Chennai Basin"
    container_height_cm: float = 30.0
    baseline_level_cm: float = 5.0
    inflow_rate: float = 0.0
    drainage_capacity: float = 0.5
    rainfall_input_mm: float = 0.0
    runoff_coefficient: float = 0.05
    upstream_inflow_cm: float = 0.0
    upstream_zone_id: Optional[str] = None
    upstream_transfer_coeff: float = 0.0
    warn_threshold_pct: float = 70.0
    crit_threshold_pct: float = 85.0
    sensor_reliability: float = 1.0
    network_availability: float = 1.0
    noise_stddev_cm: float = 0.0
    conceptual_topology: str = (
        "Conceptual lumped water-balance model informed by Chennai sub-basin boundaries; "
        "not an uncalibrated 2D hydrodynamic simulation."
    )

    current_level_cm: float = field(init=False, default=0.0)
    step_count: int = field(init=False, default=0)
    _rng: random.Random = field(init=False, repr=False, default=None)

    def __post_init__(self):
        self.current_level_cm = self.baseline_level_cm
        self._rng = random.Random(hash(self.zone_id))

    def reset(self, seed: Optional[int] = None):
        self.current_level_cm = self.baseline_level_cm
        self.step_count = 0
        if seed is not None:
            self._rng = random.Random(seed)

    def step(self, dt_sec: float = BASE_DT_SEC) -> ZoneReading:
        scale = dt_sec / BASE_DT_SEC

        effective_drain = min(self.drainage_capacity * scale, self.current_level_cm)
        rainfall_inflow = (self.rainfall_input_mm * self.runoff_coefficient) * scale
        inflow = (self.inflow_rate + self.upstream_inflow_cm) * scale + rainfall_inflow
        self.current_level_cm += inflow - effective_drain
        self.current_level_cm = max(0.0, min(self.current_level_cm, self.container_height_cm))
        self.step_count += 1

        true_level = self.current_level_cm
        true_pct = (true_level / self.container_height_cm) * 100.0 if self.container_height_cm > 0 else 0.0

        sensor_ok = self._rng.random() < self.sensor_reliability
        network_ok = self._rng.random() < self.network_availability

        observed_level: Optional[float] = None
        observed_pct: Optional[float] = None
        sensor_status = "valid"
        quality_flags = []

        if sensor_ok:
            noise = self._rng.gauss(0, self.noise_stddev_cm) if self.noise_stddev_cm > 0 else 0.0
            observed_level = max(0.0, min(true_level + noise, self.container_height_cm))
            observed_pct = (observed_level / self.container_height_cm) * 100.0
            if abs(noise) > 0.5:
                quality_flags.append("noisy")
        else:
            sensor_status = "invalid"
            quality_flags.append("sensor_failure")

        if not network_ok:
            sensor_status = "offline"
            quality_flags.append("network_dropout")

        alert_level = "normal"
        if true_pct >= self.crit_threshold_pct:
            alert_level = "critical"
        elif true_pct >= self.warn_threshold_pct:
            alert_level = "warning"

        return ZoneReading(
            zone_id=self.zone_id,
            step=self.step_count,
            timestamp=datetime.now(timezone.utc),
            true_level_cm=round(true_level, 2),
            true_level_pct=round(true_pct, 2),
            observed_level_cm=round(observed_level, 2) if observed_level is not None else None,
            observed_level_pct=round(observed_pct, 2) if observed_pct is not None else None,
            sensor_ok=sensor_ok,
            network_ok=network_ok,
            sensor_status=sensor_status,
            alert_level=alert_level,
            quality_flags=quality_flags,
        )

    @property
    def level_pct(self) -> float:
        if self.container_height_cm <= 0:
            return 0.0
        return (self.current_level_cm / self.container_height_cm) * 100.0


class DigitalTwinEngine:
    """Manages zone simulations and applies scenario mutations."""

    def __init__(self, seed: int = 42):
        self._zones: dict[str, ZoneModel] = {}
        self._seed = seed
        self._global_step = 0
        self._history: dict[str, list[ZoneReading]] = {}
        logger.info("DigitalTwinEngine initialized with seed=%d", seed)

    @property
    def zones(self) -> dict[str, ZoneModel]:
        return dict(self._zones)

    @property
    def global_step(self) -> int:
        return self._global_step

    def add_zone(self, zone: ZoneModel):
        zone.reset(seed=self._seed + (hash(zone.zone_id) % 10000))
        self._zones[zone.zone_id] = zone
        self._history[zone.zone_id] = []

    def remove_zone(self, zone_id: str):
        self._zones.pop(zone_id, None)
        self._history.pop(zone_id, None)

    def reset_all(self):
        self._global_step = 0
        for zone_id, zone in self._zones.items():
            zone.reset(seed=self._seed + (hash(zone_id) % 10000))
            self._history[zone_id] = []

    def step_all(self, dt_sec: float = BASE_DT_SEC) -> list[ZoneReading]:
        self._global_step += 1
        readings = []
        for zone_id, zone in self._zones.items():
            reading = zone.step(dt_sec)
            self._history[zone_id].append(reading)
            readings.append(reading)
        return readings

    ZONE_ALIASES = {
        "zone_adyar": "zone_01",
        "zone_cooum": "zone_02",
        "zone_kosasthalaiyar": "zone_03",
    }

    def _resolve_id(self, zone_id: str) -> str:
        return self.ZONE_ALIASES.get(zone_id, zone_id)

    def get_zone_state(self, zone_id: str) -> Optional[dict]:
        target_id = self._resolve_id(zone_id)
        zone = self._zones.get(target_id)
        if not zone:
            return None
        return {
            "zone_id": zone.zone_id,
            "zone_name": zone.zone_name,
            "subbasin": zone.subbasin,
            "current_level_cm": round(zone.current_level_cm, 2),
            "current_level_pct": round(zone.level_pct, 2),
            "container_height_cm": zone.container_height_cm,
            "inflow_rate": zone.inflow_rate,
            "drainage_capacity": zone.drainage_capacity,
            "rainfall_input_mm": zone.rainfall_input_mm,
            "upstream_inflow_cm": zone.upstream_inflow_cm,
            "step_count": zone.step_count,
            "conceptual_topology": zone.conceptual_topology,
        }

    def get_all_states(self) -> list[dict]:
        return [self.get_zone_state(zid) for zid in self._zones if self.get_zone_state(zid)]

    def get_history(self, zone_id: str) -> list[dict]:
        target_id = self._resolve_id(zone_id)
        return [r.to_dict() for r in self._history.get(target_id, [])]

    def apply_scenario_params(self, zone_id: str, **params):
        target_id = self._resolve_id(zone_id)
        zone = self._zones.get(target_id)
        if not zone:
            logger.warning("Zone '%s' (resolved '%s') not found for parameter update", zone_id, target_id)
            return

        for key, value in params.items():
            if hasattr(zone, key):
                setattr(zone, key, value)
            else:
                logger.warning("Unknown zone parameter '%s'", key)


def create_default_zones() -> list[ZoneModel]:
    return [
        ZoneModel(
            zone_id="zone_01",
            zone_name="Adyar Basin (Saidapet / Chembarambakkam Corridor)",
            subbasin="Adyar",
            container_height_cm=30.0,
            baseline_level_cm=5.0,
            inflow_rate=0.1,
            drainage_capacity=0.5,
            warn_threshold_pct=70.0,
            crit_threshold_pct=85.0,
            sensor_reliability=1.0,
            network_availability=1.0,
            noise_stddev_cm=0.2,
        ),
        ZoneModel(
            zone_id="zone_02",
            zone_name="Cooum Basin (Nungambakkam / Central Urban Drain)",
            subbasin="Cooum",
            container_height_cm=25.0,
            baseline_level_cm=3.0,
            inflow_rate=0.05,
            drainage_capacity=0.4,
            warn_threshold_pct=70.0,
            crit_threshold_pct=85.0,
            sensor_reliability=0.95,
            network_availability=1.0,
            noise_stddev_cm=0.3,
        ),
        ZoneModel(
            zone_id="zone_03",
            zone_name="Kosasthalaiyar Basin (North Chennai / Ennore Corridor)",
            subbasin="Kosasthalaiyar",
            container_height_cm=40.0,
            baseline_level_cm=8.0,
            inflow_rate=0.08,
            drainage_capacity=0.6,
            warn_threshold_pct=65.0,
            crit_threshold_pct=80.0,
            sensor_reliability=0.90,
            network_availability=0.95,
            noise_stddev_cm=0.4,
        ),
    ]
