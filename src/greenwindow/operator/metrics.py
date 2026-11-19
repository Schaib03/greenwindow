from prometheus_client import Counter, Gauge, Histogram, start_http_server

GRID_INTENSITY = Gauge(
    "greenwindow_grid_intensity_gco2_per_kwh",
    "Current grid carbon intensity from the forecast.",
    ["zone", "source"],
)
JOBS_SCHEDULED = Counter(
    "greenwindow_jobs_scheduled_total", "Carbon-aware jobs planned.", ["zone", "reason"]
)
JOBS_STARTED = Counter("greenwindow_jobs_started_total", "Jobs created.", ["zone"])
JOBS_FINISHED = Counter("greenwindow_jobs_finished_total", "Jobs finished.", ["zone", "phase"])
AVOIDED_GRAMS = Counter(
    "greenwindow_avoided_co2_grams_total",
    "Estimated CO2 avoided by shifting jobs, in grams.",
    ["zone"],
)
START_DELAY = Histogram(
    "greenwindow_start_delay_seconds",
    "How long jobs were held before starting.",
    ["zone"],
    buckets=(0, 60, 300, 900, 1800, 3600, 7200, 14400, 28800, 57600),
)


def serve(port: int) -> None:
    start_http_server(port)
