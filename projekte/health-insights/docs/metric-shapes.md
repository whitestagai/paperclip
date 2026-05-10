# Health Auto Export — Metric Shapes Reference

Health Auto Export by Ifunography exports metrics already as canonical
snake_case names — no Apple Health identifier mapping is needed. The JSON
shape *of each sample* varies by metric type, though.

## Sample shapes (verified from real exports 2026-05-09)

### Shape A: Simple quantity (27 of 29 metrics)

```json
{ "date": "2026-05-09 16:39:00 +0200", "qty": 9.218, "source": "Ultra 3" }
```

Metrics with this shape (non-exhaustive): `step_count`, `active_energy`,
`basal_energy_burned`, `flights_climbed`, `apple_exercise_time`,
`apple_stand_hour`, `apple_stand_time`, `heart_rate_variability`,
`resting_heart_rate`, `respiratory_rate`, `blood_oxygen_saturation`,
`blood_glucose`, `mindful_minutes`, `breathing_disturbances`,
`time_in_daylight`, `environmental_audio_exposure`, `headphone_audio_exposure`,
`walking_running_distance`, `walking_speed`, `walking_step_length`,
`walking_heart_rate_average`, `walking_asymmetry_percentage`,
`walking_double_support_percentage`, `stair_speed_up`, `stair_speed_down`,
`physical_effort`, `apple_sleeping_wrist_temperature`.

### Shape B: HR aggregate (1 metric: `heart_rate`)

```json
{ "date": "2026-05-09 00:07:00 +0200", "source": "Ultra 3",
  "Min": 68, "Max": 68, "Avg": 68 }
```

For `heart_rate` we store `Avg` as the canonical value. Daily aggregate's
`MIN(value)` / `MAX(value)` / `AVG(value)` over all 5-minute Avg samples
gives a useful daily summary.

### Shape C: Sleep session (1 metric: `sleep_analysis`)

```json
{ "date": "2026-05-09 00:00:00 +0200", "source": "Ultra 3",
  "totalSleep": 5.17, "core": 3.50, "deep": 0.27, "rem": 1.41,
  "awake": 0.44, "asleep": 0,
  "inBedStart": "...", "sleepStart": "...", "sleepEnd": "...", "inBedEnd": "...", "inBed": 0 }
```

Values are in **hours**. We explode each sleep sample into six canonical
metrics: `sleep_total_hours`, `sleep_core_hours`, `sleep_deep_hours`,
`sleep_rem_hours`, `sleep_awake_hours`, `sleep_in_bed_hours`.

## Date format

All `date` fields use `"YYYY-MM-DD HH:MM:SS +ZZZZ"` (with a space, not the
ISO-8601 `T`). Postgres `TIMESTAMPTZ` accepts this directly without
preprocessing — pass the raw string to a `$N::timestamptz` parameter.

## Unit normalization

Health Auto Export emits `active_energy` and `basal_energy_burned` in **kJ**,
not kcal. We rename to `active_energy_kcal` / `basal_energy_kcal` and
divide by 4.184 during normalization so canonical metrics are always in kcal.

## Aggregation choices

- **Cumulative (daily sum):** `step_count`, `active_energy_kcal`,
  `basal_energy_kcal`, `flights_climbed`, `apple_exercise_time`,
  `apple_stand_time`, `time_in_daylight`, `mindful_minutes`,
  `walking_running_distance`, `breathing_disturbances`,
  `sleep_*_hours`
- **Instant readings (daily avg + min + max):** `heart_rate`,
  `heart_rate_variability`, `respiratory_rate`, `blood_oxygen_saturation`,
  `walking_speed`, `walking_step_length`, `walking_heart_rate_average`,
  `apple_sleeping_wrist_temperature`, `environmental_audio_exposure`,
  `headphone_audio_exposure`, `physical_effort`, `stair_speed_up`,
  `stair_speed_down`, `walking_asymmetry_percentage`,
  `walking_double_support_percentage`, `blood_glucose`
- **Daily-frequency (avg only):** `resting_heart_rate`, `apple_stand_hour`

## Workouts

Health Auto Export's daily JSON does NOT include workouts by default.
Workouts in `AutoSync/Workouts/*.hae` are LZFSE-compressed and not directly
readable by n8n. Two options:

- **Recommended:** in Health Auto Export iPhone app → Daily Export config →
  enable "Workouts" so they appear in `data.workouts[]` of the daily JSON
- **Fallback:** defer workouts to Phase 2 (the `get_workouts` MCP tool
  already handles empty results gracefully)

If workouts are enabled, verify the daily-export shape with:
```bash
jq '.data.workouts[0]' "<latest>.json"
```
