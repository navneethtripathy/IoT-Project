"""
CivicTwin-R — Controlled Numerical Verification Tests for 2D Terrain Hydrology

Implements all 12 mandatory numerical verification checks specified in Section 14:
  1. Zero rainfall + zero initial depth creates zero water.
  2. Uniform rainfall in closed domain preserves mass balance.
  3. Water depth never becomes negative.
  4. Sloped terrain routes water consistently downhill.
  5. Topographic depression (bowl) accumulates and retains water.
  6. Known drainage sink reduces stored water accurately.
  7. Nodata cells never behave as water sources or sinks.
  8. Identical inputs produce identical deterministic outputs.
  9. Smaller internal time steps produce convergent solutions.
 10. Scenario outputs respond monotonically to rainfall & drainage inputs.
 11. Open boundary outflow is explicitly tracked in volume balance.
 12. Extreme inputs are validated / bounded safely without NaN/Inf.
"""

import numpy as np
import pytest

from digital_twin.terrain_hydrology import (
    ChennaiTerrainTwinEngine,
    HydroScenarioConfig,
    PREDEFINED_SCENARIOS,
    run_controlled_overland_grid,
)


class TestControlledNumericalHydrology:
    """12 required controlled mathematical & physical tests for the 2D Landlab solver."""

    def test_01_zero_rainfall_zero_initial_creates_no_water(self):
        z = np.full((24, 24), 5.0)
        res = run_controlled_overland_grid(z, dx_m=100.0, rain_schedule_mm_hr=(0.0,), step_durations_sec=(1800.0,))
        assert float(res["final_depth_m"].max()) == 0.0
        assert res["mass_balance"]["v_final_m3"] == 0.0
        assert res["mass_balance"]["residual_m3"] == 0.0

    def test_02_uniform_rainfall_closed_domain_mass_balance(self):
        z = np.full((24, 24), 10.0)
        res = run_controlled_overland_grid(
            z, dx_m=100.0, rain_schedule_mm_hr=(60.0,), step_durations_sec=(1800.0,)
        )
        mb = res["mass_balance"]
        assert mb["v_rain_m3"] > 0.0
        assert mb["relative_error"] < 1e-4, f"Mass balance error too high: {mb}"

    def test_03_nonnegative_water_depth_under_strong_sinks(self):
        z = np.linspace(10.0, 2.0, 25)[None, :].repeat(25, axis=0)
        drain_map = np.full((25, 25), 150.0)  # Strong 150 mm/hr drainage > 20 mm/hr rain
        res = run_controlled_overland_grid(
            z,
            dx_m=100.0,
            rain_schedule_mm_hr=(20.0, 0.0),
            step_durations_sec=(600.0, 1200.0),
            infiltration_rate_mm_hr=80.0,
            drain_rate_2d_mm_hr=drain_map,
        )
        assert float(res["final_depth_m"].min()) >= 0.0
        assert np.all(np.isfinite(res["final_depth_m"]))

    def test_04_sloped_terrain_routes_downhill(self):
        # West (col 0) = 15m -> East (col 29) = 0m; East rim open
        yy, xx = np.mgrid[0:20, 0:30]
        z = 15.0 * (1.0 - xx / 29.0)
        open_mask = np.zeros((20, 30), dtype=bool)
        open_mask[1:-1, -1] = True  # Open coastal boundary on East
        res = run_controlled_overland_grid(
            z,
            dx_m=100.0,
            open_boundary_mask_2d=open_mask,
            rain_schedule_mm_hr=(0.0,),
            step_durations_sec=(900.0,),
            initial_depth_2d=np.full((20, 30), 0.15),
        )
        h = res["final_depth_m"]
        west_depth = float(h[2:-2, 2:6].mean())
        east_depth = float(h[2:-2, -6:-2].mean())
        assert east_depth > west_depth, f"Expected downhill East deeper than West: east={east_depth}, west={west_depth}"
        assert float(res["qx_m2_s"][2:-2, 2:-2].mean()) > 0.0, "Mean Eastward x-discharge should be positive"

    def test_05_depression_accumulates_water(self):
        yy, xx = np.mgrid[0:25, 0:25]
        # Saucer depression centered at (12, 12)
        z = 0.02 * ((yy - 12.0) ** 2 + (xx - 12.0) ** 2)
        res = run_controlled_overland_grid(
            z,
            dx_m=100.0,
            rain_schedule_mm_hr=(50.0,),
            step_durations_sec=(1800.0,),
        )
        h = res["final_depth_m"]
        center_h = float(h[11:14, 11:14].mean())
        slope_rim_h = float(h[2:5, 2:5].mean())
        assert center_h > slope_rim_h * 1.5, f"Depression center ({center_h:.3f}m) should exceed upper rim ({slope_rim_h:.3f}m)"

    def test_06_drainage_removal_reduces_stored_water(self):
        z = np.full((20, 20), 5.0)
        res_nodrain = run_controlled_overland_grid(z, dx_m=100.0, rain_schedule_mm_hr=(40.0,), step_durations_sec=(1800.0,))
        res_drain = run_controlled_overland_grid(
            z,
            dx_m=100.0,
            rain_schedule_mm_hr=(40.0,),
            step_durations_sec=(1800.0,),
            drain_rate_2d_mm_hr=np.full((20, 20), 15.0),
        )
        assert res_drain["mass_balance"]["v_drain_m3"] > 0.0
        assert res_drain["mass_balance"]["v_final_m3"] < res_nodrain["mass_balance"]["v_final_m3"]
        # Exact theoretical expected removal: 15 mm/hr * 0.5 hr = 0.0075 m * (18*18 * 10000 m^2)
        expected_drain = 0.0075 * (18 * 18 * 10000.0)
        assert res_drain["mass_balance"]["v_drain_m3"] == pytest.approx(expected_drain, rel=1e-4)

    def test_07_nodata_cells_inactive_no_leak_or_storage(self):
        yy, xx = np.mgrid[0:22, 0:22]
        z = np.full((22, 22), 5.0)
        valid = np.ones((22, 22), dtype=bool)
        # Carve an interior block of nodata pixels (e.g., masked hill or quarry)
        nodata_block = (yy >= 8) & (yy <= 12) & (xx >= 8) & (xx <= 12)
        valid[nodata_block] = False
        z[nodata_block] = -9999.0  # Sentinel nodata elevation
        res = run_controlled_overland_grid(
            z,
            dx_m=100.0,
            valid_mask_2d=valid,
            rain_schedule_mm_hr=(50.0,),
            step_durations_sec=(1800.0,),
        )
        assert float(res["final_depth_m"][nodata_block].max()) == 0.0
        assert float(res["final_depth_m"][nodata_block].min()) == 0.0
        assert res["mass_balance"]["relative_error"] < 1e-4

    def test_08_determinism_identical_inputs_exact_repeatability(self):
        yy, xx = np.mgrid[0:22, 0:22]
        z = 5.0 + 0.01 * ((yy - 10) ** 2 + (xx - 14) ** 2)
        kwargs = dict(elevation_2d=z, dx_m=120.0, rain_schedule_mm_hr=(45.0, 20.0), step_durations_sec=(900.0, 900.0))
        r1 = run_controlled_overland_grid(**kwargs)
        r2 = run_controlled_overland_grid(**kwargs)
        np.testing.assert_array_equal(r1["final_depth_m"], r2["final_depth_m"])
        assert r1["mass_balance"] == r2["mass_balance"]

    def test_09_timestep_convergence(self):
        yy, xx = np.mgrid[0:22, 0:22]
        z = 0.02 * ((yy - 11.0) ** 2 + (xx - 11.0) ** 2)
        h_init = np.full((22, 22), 0.12)
        r_coarse = run_controlled_overland_grid(z, dx_m=100.0, step_durations_sec=(600.0,), initial_depth_2d=h_init, max_internal_dt=30.0)
        r_mid = run_controlled_overland_grid(z, dx_m=100.0, step_durations_sec=(600.0,), initial_depth_2d=h_init, max_internal_dt=5.0)
        r_fine = run_controlled_overland_grid(z, dx_m=100.0, step_durations_sec=(600.0,), initial_depth_2d=h_init, max_internal_dt=1.0)
        err_coarse = float(np.sqrt(np.mean((r_coarse["final_depth_m"] - r_fine["final_depth_m"]) ** 2)))
        err_mid = float(np.sqrt(np.mean((r_mid["final_depth_m"] - r_fine["final_depth_m"]) ** 2)))
        assert err_mid <= err_coarse + 1e-4
        assert err_mid < 0.01

    def test_10_real_chennai_dem_scenario_monotonic_response(self):
        eng = ChennaiTerrainTwinEngine()
        r_norm = eng.run_scenario(PREDEFINED_SCENARIOS["normal"])
        r_heavy = eng.run_scenario(PREDEFINED_SCENARIOS["heavy_rainfall"])
        r_extr = eng.run_scenario(PREDEFINED_SCENARIOS["extreme_rainfall"])
        r_red = eng.run_scenario(PREDEFINED_SCENARIOS["reduced_drainage"])
        r_imp = eng.run_scenario(PREDEFINED_SCENARIOS["improved_drainage"])

        assert r_norm["summary"]["stored_water_volume_mcm"] == 0.0
        assert r_norm["summary"]["urban_inundated_area_km2"] == 0.0
        assert r_heavy["summary"]["stored_water_volume_mcm"] > r_norm["summary"]["stored_water_volume_mcm"]
        assert r_extr["summary"]["stored_water_volume_mcm"] > r_heavy["summary"]["stored_water_volume_mcm"]
        # Drainage sensitivity on identical 45 mm/hr 4h rain:
        assert r_red["summary"]["stored_water_volume_mcm"] > r_heavy["summary"]["stored_water_volume_mcm"]
        assert r_imp["summary"]["stored_water_volume_mcm"] < r_heavy["summary"]["stored_water_volume_mcm"]

    def test_11_open_boundary_outflow_in_global_volume_balance(self):
        yy, xx = np.mgrid[0:24, 0:28]
        z = 8.0 * (1.0 - xx / 27.0)
        open_mask = np.zeros((24, 28), dtype=bool)
        open_mask[1:-1, -1] = True
        res = run_controlled_overland_grid(
            z,
            dx_m=100.0,
            open_boundary_mask_2d=open_mask,
            rain_schedule_mm_hr=(60.0,),
            step_durations_sec=(1800.0,),
        )
        mb = res["mass_balance"]
        assert mb["v_outflow_m3"] > 0.0, "Water should actively exit across the East coastal open boundary"
        assert mb["relative_error"] < 1e-4, f"Global open-boundary mass balance residual too high: {mb}"

    def test_12_extreme_inputs_and_parameter_validation(self):
        # Negative rainfall rejected safely
        bad_cfg = HydroScenarioConfig(
            scenario_id="invalid",
            scenario_name="Invalid",
            mode="scenario_simulation",
            rainfall_intensity_mm_hr=-10.0,
            duration_hours=2.0,
            infiltration_rate_mm_hr=2.0,
            drainage_efficiency_pct=100.0,
        )
        with pytest.raises(ValueError):
            bad_cfg.validate()

        # High storm stress run remains completely finite on real Chennai DEM
        eng = ChennaiTerrainTwinEngine()
        stress = HydroScenarioConfig(
            scenario_id="stress",
            scenario_name="Stress 150mm/hr",
            mode="scenario_simulation",
            rainfall_intensity_mm_hr=150.0,
            duration_hours=4.0,
            infiltration_rate_mm_hr=1.0,
            drainage_efficiency_pct=0.0,
        )
        r_stress = eng.run_scenario(stress)
        assert np.all(np.isfinite(r_stress["_final_depth_grid"]))
        assert r_stress["summary"]["mass_balance"]["relative_error"] < 0.005
