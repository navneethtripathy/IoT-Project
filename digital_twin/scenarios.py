"""
CivicTwin-R — Scenario Definitions and Controller

Defines configurable flood-monitoring scenarios that modify zone parameters
over a scripted timeline. Each scenario is deterministic (given the same seed)
and produces a labelled output dataset.

Scenarios:
    1. normal          — Baseline conditions, no disruptions.
    2. heavy_rainfall  — Rapid inflow increase simulating heavy rain.
    3. blocked_drain   — Reduced drainage capacity.
    4. sudden_rise     — Step-change water-level jump.
    5. sensor_dropout  — Intermittent sensor failures.
    6. noisy_sensor    — Increased measurement noise and bias.
    7. network_outage  — Simulated connectivity loss and recovery.
    8. multi_zone_stress — Multiple zones under stress simultaneously.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from digital_twin.model import DigitalTwinEngine, ZoneModel

logger = logging.getLogger("civictwin.twin.scenarios")


@dataclass
class ScenarioPhase:
    """A single phase within a scenario timeline."""

    start_step: int
    end_step: int
    zone_id: str
    params: dict = field(default_factory=dict)
    description: str = ""


@dataclass
class ScenarioDefinition:
    """Complete scenario specification."""

    scenario_id: str
    name: str
    description: str
    total_steps: int
    phases: list[ScenarioPhase] = field(default_factory=list)


# ── Predefined Scenarios ─────────────────────────────────

SCENARIOS: dict[str, ScenarioDefinition] = {
    "normal": ScenarioDefinition(
        scenario_id="normal",
        name="Normal Conditions",
        description="Baseline monitoring — stable inflow, full drainage, reliable sensors.",
        total_steps=200,
        phases=[],  # No parameter changes
    ),
    "heavy_rainfall": ScenarioDefinition(
        scenario_id="heavy_rainfall",
        name="Heavy Rainfall",
        description="Simulates a sudden increase in water inflow across zones, "
                    "representing a heavy rainfall event.",
        total_steps=300,
        phases=[
            ScenarioPhase(
                start_step=50, end_step=150, zone_id="zone_01",
                params={"inflow_rate": 1.5},
                description="Heavy inflow to Riverside Canal",
            ),
            ScenarioPhase(
                start_step=60, end_step=160, zone_id="zone_02",
                params={"inflow_rate": 1.2},
                description="Heavy inflow to Downtown Storm Drain",
            ),
            ScenarioPhase(
                start_step=70, end_step=170, zone_id="zone_03",
                params={"inflow_rate": 1.0},
                description="Heavy inflow to Suburban Retention Basin",
            ),
        ],
    ),
    "blocked_drain": ScenarioDefinition(
        scenario_id="blocked_drain",
        name="Blocked Drain",
        description="Drainage capacity drops sharply in zone_01, simulating a blocked drain.",
        total_steps=250,
        phases=[
            ScenarioPhase(
                start_step=40, end_step=180, zone_id="zone_01",
                params={"drainage_capacity": 0.05, "inflow_rate": 0.6},
                description="Drain blocked, moderate inflow continues",
            ),
        ],
    ),
    "sudden_rise": ScenarioDefinition(
        scenario_id="sudden_rise",
        name="Sudden Water Rise",
        description="Abrupt large inflow spike in zone_02, simulating flash-flood conditions.",
        total_steps=200,
        phases=[
            ScenarioPhase(
                start_step=30, end_step=50, zone_id="zone_02",
                params={"inflow_rate": 3.0},
                description="Flash inflow spike",
            ),
            ScenarioPhase(
                start_step=50, end_step=200, zone_id="zone_02",
                params={"inflow_rate": 0.2},
                description="Inflow subsides",
            ),
        ],
    ),
    "sensor_dropout": ScenarioDefinition(
        scenario_id="sensor_dropout",
        name="Sensor Dropout",
        description="Zone_01 sensor reliability drops to simulate intermittent sensor failures.",
        total_steps=250,
        phases=[
            ScenarioPhase(
                start_step=50, end_step=150, zone_id="zone_01",
                params={"sensor_reliability": 0.3},
                description="Sensor becomes unreliable (30% success rate)",
            ),
            ScenarioPhase(
                start_step=150, end_step=250, zone_id="zone_01",
                params={"sensor_reliability": 1.0},
                description="Sensor restored",
            ),
        ],
    ),
    "noisy_sensor": ScenarioDefinition(
        scenario_id="noisy_sensor",
        name="Noisy Sensor",
        description="Increased measurement noise on zone_02 sensor.",
        total_steps=200,
        phases=[
            ScenarioPhase(
                start_step=30, end_step=170, zone_id="zone_02",
                params={"noise_stddev_cm": 2.0},
                description="High sensor noise (±2cm stddev)",
            ),
        ],
    ),
    "network_outage": ScenarioDefinition(
        scenario_id="network_outage",
        name="Network Outage & Recovery",
        description="Zone_01 loses network connectivity, then recovers.",
        total_steps=250,
        phases=[
            ScenarioPhase(
                start_step=60, end_step=140, zone_id="zone_01",
                params={"network_availability": 0.0},
                description="Complete network loss",
            ),
            ScenarioPhase(
                start_step=140, end_step=250, zone_id="zone_01",
                params={"network_availability": 1.0},
                description="Network recovered",
            ),
        ],
    ),
    "multi_zone_stress": ScenarioDefinition(
        scenario_id="multi_zone_stress",
        name="Multi-Zone Stress Test",
        description="Simultaneous heavy rainfall, sensor failures, and network issues across zones.",
        total_steps=350,
        phases=[
            # Heavy rain on all zones
            ScenarioPhase(
                start_step=50, end_step=200, zone_id="zone_01",
                params={"inflow_rate": 1.8},
                description="Heavy rainfall - Zone 1",
            ),
            ScenarioPhase(
                start_step=60, end_step=210, zone_id="zone_02",
                params={"inflow_rate": 1.5, "drainage_capacity": 0.1},
                description="Heavy rainfall + blocked drain - Zone 2",
            ),
            ScenarioPhase(
                start_step=70, end_step=180, zone_id="zone_03",
                params={"inflow_rate": 1.2, "sensor_reliability": 0.4},
                description="Heavy rainfall + sensor issues - Zone 3",
            ),
            # Network outage on zone_01
            ScenarioPhase(
                start_step=100, end_step=160, zone_id="zone_01",
                params={"network_availability": 0.0},
                description="Network outage - Zone 1",
            ),
            # Recovery
            ScenarioPhase(
                start_step=200, end_step=350, zone_id="zone_01",
                params={"inflow_rate": 0.1, "network_availability": 1.0},
                description="Recovery - Zone 1",
            ),
            ScenarioPhase(
                start_step=210, end_step=350, zone_id="zone_02",
                params={"inflow_rate": 0.05, "drainage_capacity": 0.4},
                description="Recovery - Zone 2",
            ),
            ScenarioPhase(
                start_step=180, end_step=350, zone_id="zone_03",
                params={"inflow_rate": 0.08, "sensor_reliability": 0.9},
                description="Recovery - Zone 3",
            ),
        ],
    ),
}


class ScenarioController:
    """
    Executes scenarios by applying phase parameters at the correct steps.

    Usage:
        controller = ScenarioController(engine)
        controller.load_scenario("heavy_rainfall")
        while not controller.is_complete:
            readings = controller.step()
    """

    def __init__(self, engine: DigitalTwinEngine):
        self._engine = engine
        self._scenario: Optional[ScenarioDefinition] = None
        self._current_step: int = 0
        self._active_params: dict[str, dict] = {}  # zone_id -> original params
        self._results: list[dict] = []
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_complete(self) -> bool:
        if not self._scenario:
            return True
        return self._current_step >= self._scenario.total_steps

    @property
    def current_step(self) -> int:
        return self._current_step

    @property
    def scenario(self) -> Optional[ScenarioDefinition]:
        return self._scenario

    @property
    def progress_pct(self) -> float:
        if not self._scenario or self._scenario.total_steps == 0:
            return 100.0
        return min(100.0, (self._current_step / self._scenario.total_steps) * 100.0)

    def load_scenario(self, scenario_id: str) -> bool:
        """Load a scenario definition and reset the engine."""
        if scenario_id not in SCENARIOS:
            logger.error("Unknown scenario: %s", scenario_id)
            return False

        self._scenario = SCENARIOS[scenario_id]
        self._current_step = 0
        self._results = []
        self._is_running = True
        self._active_params = {}

        # Save original zone parameters for restoration
        for zone_id, zone in self._engine.zones.items():
            self._active_params[zone_id] = {
                "inflow_rate": zone.inflow_rate,
                "drainage_capacity": zone.drainage_capacity,
                "sensor_reliability": zone.sensor_reliability,
                "network_availability": zone.network_availability,
                "noise_stddev_cm": zone.noise_stddev_cm,
            }

        self._engine.reset_all()
        logger.info("Scenario '%s' loaded (%d steps)", scenario_id, self._scenario.total_steps)
        return True

    def step(self, dt_sec: float = 5.0) -> list[dict]:
        """Execute one simulation step, applying scenario phases as needed."""
        if not self._scenario or self.is_complete:
            return []

        self._current_step += 1

        # Apply or revert phase parameters
        for phase in self._scenario.phases:
            if self._current_step == phase.start_step:
                logger.debug(
                    "Step %d: Applying phase '%s' to %s",
                    self._current_step, phase.description, phase.zone_id,
                )
                self._engine.apply_scenario_params(phase.zone_id, **phase.params)
            elif self._current_step == phase.end_step:
                # Restore original params
                original = self._active_params.get(phase.zone_id, {})
                restore_params = {k: original[k] for k in phase.params if k in original}
                if restore_params:
                    logger.debug(
                        "Step %d: Reverting phase '%s' on %s",
                        self._current_step, phase.description, phase.zone_id,
                    )
                    self._engine.apply_scenario_params(phase.zone_id, **restore_params)

        # Run simulation step
        readings = self._engine.step_all(dt_sec)
        step_data = []
        for r in readings:
            d = r.to_dict()
            d["scenario_id"] = self._scenario.scenario_id
            d["scenario_step"] = self._current_step
            step_data.append(d)
        self._results.extend(step_data)

        if self.is_complete:
            self._is_running = False
            logger.info("Scenario '%s' completed", self._scenario.scenario_id)

        return step_data

    def stop(self):
        """Stop the current scenario and restore original parameters."""
        if self._scenario and self._is_running:
            # Restore all original params
            for zone_id, orig in self._active_params.items():
                self._engine.apply_scenario_params(zone_id, **orig)
            self._is_running = False
            logger.info("Scenario '%s' stopped at step %d", self._scenario.scenario_id, self._current_step)

    def get_results(self) -> list[dict]:
        """Return all recorded results for the current/last scenario."""
        return list(self._results)

    def get_summary(self) -> dict:
        """Return a summary of the scenario run."""
        if not self._scenario:
            return {"status": "no_scenario_loaded"}

        return {
            "scenario_id": self._scenario.scenario_id,
            "scenario_name": self._scenario.name,
            "total_steps": self._scenario.total_steps,
            "current_step": self._current_step,
            "progress_pct": round(self.progress_pct, 1),
            "is_running": self._is_running,
            "is_complete": self.is_complete,
            "results_count": len(self._results),
        }


def list_scenarios() -> list[dict]:
    """List all available scenario definitions."""
    return [
        {
            "scenario_id": s.scenario_id,
            "name": s.name,
            "description": s.description,
            "total_steps": s.total_steps,
            "phases_count": len(s.phases),
        }
        for s in SCENARIOS.values()
    ]
