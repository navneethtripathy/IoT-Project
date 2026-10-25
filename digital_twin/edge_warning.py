"""
CivicTwin-R — Testable Pure-Python Edge Warning & Hysteresis Evaluator
Mirrors the ESP32 firmware embedded C++ threshold, hysteresis, and LED logic.

Allows automated validation of:
- Warning and critical threshold transitions
- Anti-chatter hysteresis retention
- Rapid surface-ripple oscillation suppression
- Sensor fault tolerance and timeout failure modes
- Independent autonomous operation
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Tuple


class EdgeAlertState(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    FAULT = "fault"


class LedIndicatorMode(str, Enum):
    OFF = "off"
    BLINK_1HZ = "blink_1hz"       # 500ms ON / 500ms OFF (Warning distinction)
    SOLID_ON = "solid_on"         # Continuous illumination (Critical)
    RAPID_STROBE = "rapid_strobe" # 5Hz fast flash (Sensor Fault)


class EdgeWarningEvaluator:
    """
    Evaluates edge-warning threshold breaches with hysteresis and sensor-fault tracking.
    Matches ESP32 firmware C++ state machine in firmware/esp32/src/main.ino.
    """

    def __init__(
        self,
        warn_threshold_pct: float = 70.0,
        crit_threshold_pct: float = 85.0,
        hysteresis_pct: float = 3.0,
        max_consecutive_faults: int = 5,
    ) -> None:
        if warn_threshold_pct >= crit_threshold_pct:
            raise ValueError("Warning threshold must be strictly less than critical threshold")
        if hysteresis_pct < 0.0:
            raise ValueError("Hysteresis percentage cannot be negative")

        self.warn_threshold_pct = float(warn_threshold_pct)
        self.crit_threshold_pct = float(crit_threshold_pct)
        self.hysteresis_pct = float(hysteresis_pct)
        self.max_consecutive_faults = int(max_consecutive_faults)

        self.current_state: EdgeAlertState = EdgeAlertState.NORMAL
        self.last_valid_level_pct: Optional[float] = None
        self.consecutive_faults: int = 0

    def evaluate(
        self,
        water_pct: Optional[float],
        is_valid: bool = True,
    ) -> Tuple[EdgeAlertState, LedIndicatorMode]:
        """
        Evaluate a single telemetry reading and return (alert_state, led_mode).
        """
        # Handle sensor fault, timeout, or invalid echo
        if not is_valid or water_pct is None or water_pct < 0.0 or water_pct > 100.0:
            self.consecutive_faults += 1
            if self.consecutive_faults >= self.max_consecutive_faults:
                self.current_state = EdgeAlertState.FAULT
                return self.current_state, LedIndicatorMode.RAPID_STROBE
            elif self.last_valid_level_pct is not None:
                # Hold last valid state briefly during minor dropouts (< max_consecutive_faults)
                return self.current_state, self._get_led_mode(self.current_state)
            else:
                self.current_state = EdgeAlertState.NORMAL
                return self.current_state, LedIndicatorMode.OFF

        # Valid reading: reset fault counter and update last valid level
        self.consecutive_faults = 0
        self.last_valid_level_pct = water_pct

        new_alert = EdgeAlertState.NORMAL

        if water_pct >= self.crit_threshold_pct:
            new_alert = EdgeAlertState.CRITICAL
        elif (
            self.current_state == EdgeAlertState.CRITICAL
            and water_pct >= (self.crit_threshold_pct - self.hysteresis_pct)
        ):
            # Retain critical state within critical hysteresis band
            new_alert = EdgeAlertState.CRITICAL
        elif water_pct >= self.warn_threshold_pct:
            new_alert = EdgeAlertState.WARNING
        elif (
            self.current_state == EdgeAlertState.WARNING
            and water_pct >= (self.warn_threshold_pct - self.hysteresis_pct)
        ):
            # Retain warning state within warning hysteresis band
            new_alert = EdgeAlertState.WARNING
        else:
            new_alert = EdgeAlertState.NORMAL

        self.current_state = new_alert
        return self.current_state, self._get_led_mode(self.current_state)

    @staticmethod
    def _get_led_mode(state: EdgeAlertState) -> LedIndicatorMode:
        if state == EdgeAlertState.CRITICAL:
            return LedIndicatorMode.SOLID_ON
        elif state == EdgeAlertState.WARNING:
            return LedIndicatorMode.BLINK_1HZ
        elif state == EdgeAlertState.FAULT:
            return LedIndicatorMode.RAPID_STROBE
        return LedIndicatorMode.OFF

    def reset(self) -> None:
        self.current_state = EdgeAlertState.NORMAL
        self.last_valid_level_pct = None
        self.consecutive_faults = 0
