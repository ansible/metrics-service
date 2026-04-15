Review task definitions and implementations for consistency issues.

Read these files and cross-reference them to find problems:

1. `apps/tasks/tasks.py` — `TASK_FUNCTIONS` registry and `TASK_METADATA` dict (contains `category`, `parameters`, `examples` per function)
2. `apps/tasks/task_groups.py` — the `TASK_GROUPS` list of `TaskGroup` instances, each containing task dicts with `function`, `cron`, `args`, etc.
3. The collector registries (the `_get_*_collectors()` functions that return dicts keyed by collector_type):
   - `apps/tasks/collectors/collect_hourly_metrics.py` — `_get_hourly_collectors()`
   - `apps/tasks/collectors/collect_snapshot_metrics.py` — `_get_snapshot_collectors()`
   - `apps/tasks/collectors/collect_daily_metrics.py` — `_get_daily_collectors()`
4. The function signatures of all task functions referenced by `TASK_FUNCTIONS` — check what `**kwargs` keys each function actually reads (via `kwargs.get()`, `kwargs.pop()`, etc.)

## Checks to perform

### 1. TASK_METADATA categories must be "Metrics"-prefixed or "Dashboard"-prefixed

The `category` field in `TASK_METADATA` (in `apps/tasks/tasks.py`) is served by the API at `apps/tasks/v1/views.py` and displayed in the dashboard UI. Every `category` value must start with either `"Metrics"` or `"Dashboard"`.

Exceptions: `"Testing"` (task-system test functions like `hello_world`) and `"Maintenance"` (shared cleanup tasks spanning metrics, dashboard, and service internals) are allowed.

Do NOT check the `category` field in `task_groups.py` task dicts — that field is internal and separate.

### 2. Every TASK_FUNCTIONS entry must have a TASK_METADATA entry

Every function name in the `TASK_FUNCTIONS` dict must also have a corresponding entry in `TASK_METADATA`. Functions missing from `TASK_METADATA` get `category: "General"` as a fallback in the API, and have no parameters or examples — flag them.

### 3. Collector examples must cover all collector_type variants (and no unknown ones)

For each collector function (`collect_hourly_metrics`, `collect_snapshot_metrics`, `collect_daily_metrics`):
- The `examples` list in its `TASK_METADATA` entry must include at least one example for every `collector_type` key defined in the corresponding `_get_*_collectors()` registry. Flag any missing collector_type variants.
- Every `collector_type` value used in examples must exist in the corresponding registry. Flag any unknown collector_type values.

### 4. Examples must not contain unknown parameters, and every parameter must appear in some example

For each function in `TASK_METADATA`:
- Every key in every example's `data` dict must correspond to either a key listed in that function's `parameters` dict in `TASK_METADATA`, OR a parameter the function actually reads from `**kwargs` (via `kwargs.get()`, `kwargs.pop()`, etc.). Flag any unknown keys. Ignore `execution_id` (injected by the runtime).
- Every declared parameter in the `parameters` dict must appear in at least one example's `data` dict. Flag any parameters that are never demonstrated in any example.

### 5. No two scheduled tasks at the same cron time

Across ALL task groups in `TASK_GROUPS`, no two tasks with `enabled: True` should share the same `cron` expression. Flag any collisions (list the task_ids and their shared cron).

### 6. Rollup processors must match collector registries

The daily rollup (`apps/tasks/collectors/daily_metrics_rollup.py`, function `_merge_hourly_rollups`) defines its own `hourly_rollup_processors` and `daily_rollup_processors` dicts. These must stay in sync with the collector registries:

- Every collector_type in `_get_hourly_collectors()` must appear in `hourly_rollup_processors` (or be explicitly commented out with a reason).
- Every collector_type in `_get_snapshot_collectors()` (except `config`, which is special-cased) must appear in `daily_rollup_processors`.
- Every collector_type in `_get_daily_collectors()` must appear in `daily_rollup_processors`.
- Conversely, every type in the rollup processor dicts must exist in the corresponding collector registry. Flag any orphaned processors.

## Output format

For each check, list what you found:
- If everything passes, say so
- If there are violations, list each one clearly with the file, the offending value, and what it should be (if obvious)

At the end, summarize the total number of issues found.
