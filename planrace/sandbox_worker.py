"""Container entrypoint for the PlanRace v2 disposable SQLite worker."""

from planrace.sandbox_v2 import worker_main

if __name__ == "__main__":
    raise SystemExit(worker_main())
