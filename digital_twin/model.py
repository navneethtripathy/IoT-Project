"""
CivicTwin-R — Digital Twin Zone Model

Implements a simplified discrete-time water-level simulation for multiple
monitoring zones. This is NOT a validated hydraulic model — it is a
controlled student prototype for demonstrating IoT digital-twin concepts.

Physics model (per time step dt in seconds):
    effective_drainage = min(drainage_capacity, current_level) * (dt / base_dt)
    next_level = current_level + (inflow_rate * dt / base_dt) - effective_drainage + noise
    next_level = clamp(next_level, 0, container_height)

Units:
    - Water levels: centimeters (cm)
    - Rates: cm per base_dt (configurable, default 5 s)
    - Percentages: 0–100 %
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("civictwin.twin.model")

# Default base time step for rate calculations
BASE_DT_SEC = 5.0


@dataclass
class ZoneModel:
    """
    Represents a single monitoring zone in the digital twin.

    Attributes:
        zone_id: Unique identifier for the zone.
        zone_name: Human-readable name.
        container_height_cm: Maximum water capacity of the channel/container.
        baseline_level_cm: Equilibrium water level under normal conditions.
        inflow_rate: Water inflow rate (cm per base_dt seconds).
        drainage_capacity: Maximum drainage rate (cm per base_dt seconds).
        warn_threshold_pct: Warning alert threshold (%).
        crit_threshold_pct: Critical alert threshold (%).
        sensor_reliability: Probability (0–1) a reading is successfully produced.
        network_availability: Probability (0–1) a reading is successfully transmitted.
        noise_stddev_cm: Gaussian noise standard deviation for sensor readings.
    """

    zone_id: str
    zone_name: str
    container_height_cm: float = 30.0
    baseline_level_cm: float = 5.0
    inflow_rate: float = 0.0
    drainage_capacity: float = 0.5
    warn_threshold_pct: float = 70.0
    crit_threshold_pct: float = 85.0
    sensor_reliability: float = 1.0
    network_availability: float = 1.0
    noise_stddev_cm: float = 0.0

    # Runtime state (not configuration)
    current_level_cm: float = field(init=False, default=0.0)
    step_count: int = field(init=False, default=0)
    _rng: random.Random = field(init=False, repr=False, default=None)

    def __post_init__(self):
        self.current_level_cm = self.baseline_level_cm
        self._rng = random.Random(hash(self.zone_id))

    def reset(self, seed: Optional[int] = None):
        """Reset zone to initial conditions."""
        self.current_level_cm = self.baseline_level_cm
        self.step_count = 0
        if seed is not None:
            self._rng = random.Random(seed)

    def step(self, dt_sec: float = BASE_DT_SEC) -> ZoneReading:
        """
        Advance the zone model by one time step.

        Returns a ZoneReading with the true level, observed level (if sensor
        succeeds), and metadata about sensor/network status.
        """
        scale = dt_sec / BASE_DT_SEC

        # Physics: inflow minus drainage
        effective_drain = min(self.drainage_capacity * scale, self.current_level_cm)
        inflow = self.inflow_rate * scale
        self.current_level_cm += inflow - effective_drain

        # Clamp to physical bounds
        self.current_level_cm = max(0.0, min(self.current_level_cm, self.container_height_cm))

        self.step_count += 1

        # True level (ground truth)
        true_level = self.current_level_cm
        true_pct = (true_level / self.container_height_cm) * 100.0 if self.container_height_cm > 0 else 0.0

        # Sensor reading (may fail or have noise)
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

        # Alert level evaluation (on true level for the model)
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


@dataclass
class ZoneReading:
    """Output of a single simulation step for one zone."""

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


class DigitalTwinEngine:
    """
    Manages multiple zone models and coordinates scenario execution.

    Usage:
        engine = DigitalTwinEngine(seed=42)
        engine.add_zone(ZoneModel(zone_id="zone_01", ...))
        engine.add_zone(ZoneModel(zone_id="zone_02", ...))

        for _ in range(100):
            readings = engine.step_all(dt_sec=5.0)
            # process readings...
    """

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
        """Register a zone model."""
        zone.reset(seed=self._seed + hash(zone.zone_id))
        self._zones[zone.zone_id] = zone
        self._history[zone.zone_id] = []
        logger.info("Zone '%s' (%s) added", zone.zone_id, zone.zone_name)

    def remove_zone(self, zone_id: str):
        """Remove a zone from the engine."""
        self._zones.pop(zone_id, None)
        self._history.pop(zone_id, None)

    def reset_all(self):
        """Reset all zones to initial conditions."""
        self._global_step = 0
        for zone_id, zone in self._zones.items():
            zone.reset(seed=self._seed + hash(zone_id))
            self._history[zone_id] = []

    def step_all(self, dt_sec: float = BASE_DT_SEC) -> list[ZoneReading]:
        """Advance all zones by one time step and return readings."""
        self._global_step += 1
        readings = []
        for zone_id, zone in self._zones.items():
            reading = zone.step(dt_sec)
            self._history[zone_id].append(reading)
            readings.append(reading)
        return readings

    def get_zone_state(self, zone_id: str) -> Optional[dict]:
        """Get current state summary for a zone."""
        zone = self._zones.get(zone_id)
        if not zone:
            return None
        return {
            "zone_id": zone.zone_id,
            "zone_name": zone.zone_name,
            "current_level_cm": round(zone.current_level_cm, 2),
            "current_level_pct": round(zone.level_pct, 2),
            "container_height_cm": zone.container_height_cm,
            "inflow_rate": zone.inflow_rate,
            "drainage_capacity": zone.drainage_capacity,
            "step_count": zone.step_count,
        }

    def get_all_states(self) -> list[dict]:
        """Get current state for all zones."""
        return [self.get_zone_state(zid) for zid in self._zones]

    def get_history(self, zone_id: str) -> list[dict]:
        """Get full history for a zone as list of dicts."""
        return [r.to_dict() for r in self._history.get(zone_id, [])]

    def apply_scenario_params(self, zone_id: str, **params):
        """
        Modify a zone's parameters mid-simulation (e.g., increase inflow).

        Supported params: inflow_rate, drainage_capacity, sensor_reliability,
        network_availability, noise_stddev_cm.
        """
        zone = self._zones.get(zone_id)
        if not zone:
            logger.warning("Zone '%s' not found for scenario param update", zone_id)
            return

        for key, value in params.items():
            if hasattr(zone, key):
                setattr(zone, key, value)
                logger.info("Zone '%s': %s = %s", zone_id, key, value)
            else:
                logger.warning("Unknown zone parameter: %s", key)


def create_default_zones() -> list[ZoneModel]:
    """Create the three default monitoring zones for demo and testing."""
    return [
        ZoneModel(
            zone_id="zone_01",
            zone_name="Riverside Canal Sensor",
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
            zone_name="Downtown Storm Drain",
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
            zone_name="Suburban Retention Basin",
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
