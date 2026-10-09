# Gongon (공온)

**Gongon** connects the Korea Meteorological Administration (KMA) forecast to a construction site's work schedule. For each scheduled task it shows whether the weather crosses the published safety and quality criteria for that type of work. The site manager makes the final call; Gongon gives them the evidence early enough to plan around it.

> Status: early development, solo project. Not yet deployed. The criteria data is partly still being checked against the original regulations (marked in the app).

## What it does

- **Site setup.** Register a site by road or lot-number address (Daum postcode search + Kakao geocoding). Gongon converts the coordinates to the KMA forecast grid.
- **Work schedule.** Add work items on a calendar: type of work, time, location. Pick several days at once.
- **Rule-based judgment.** For every scheduled hour, the forecast (wind, rain, snow, temperature, heat index) is compared with the criteria for that work type. Each task gets one of four verdicts:

  | Verdict | Meaning |
  | --- | --- |
  | 진행 (Proceed) | No hour meets a criterion |
  | 확인 필요 (Check) | Needs a human check: criterion not yet confirmed, forecast ambiguous, or value estimated |
  | 중지 검토 (Review stop) | A forecast value meets a criterion |
  | 판정 불가 (Unavailable) | No forecast to compare |

- **7-day Gongon Index.** A 0–100 score per day: hourly verdict points, lowered when a value is close to a threshold, when the chance of rain is high for rain-sensitive work, or when the latest forecast changed the verdict. It is capped so it never contradicts the verdicts. Days 6–7 use the mid-range forecast as a reference only and get no score.
- **Evidence.** Every judgment stores the forecast issue time, rule version and per-hour values, so you can see why a verdict was given.
- **Hourly refresh.** New forecasts are picked up automatically. Identical forecasts are fetched once per grid and reused across sites.

Judgments are deterministic: the same input and rule version always give the same result. There is no LLM or machine learning in the product.

## Work types and sources

| Work type | Rule file | Source |
| --- | --- | --- |
| Steel erection | `rules/steel.yaml` | Occupational Safety and Health Standards Rules, Art. 383 |
| Concrete placing | `rules/concrete.yaml` | KCS 14 20 41 (rain, hot weather) |
| Heat (all sites) | `rules/heat.yaml` | KMA heat index |

Other work types can be selected but show 확인 필요 until their criteria are confirmed. See `docs/references.md` for the exact sources and verification status.

## Tech stack

- Python 3.12, FastAPI, Jinja2 (server-rendered pages)
- PostgreSQL 17, SQLAlchemy 2, Alembic
- Tooling: uv, ruff, mypy, pytest

## Getting started

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), PostgreSQL 17.

```bash
uv sync --locked
cp .env.example .env    # fill in the values below
```

Create two databases (`gongon`, `gongon_test`) and set in `.env`:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` / `TEST_DATABASE_URL` | PostgreSQL connection strings |
| `KMA_SERVICE_KEY` or `KMA_APIHUB_KEY` | KMA short-range forecast API key (data.go.kr or KMA API Hub) |
| `KAKAO_REST_API_KEY` | Address → coordinates (optional; you can type coordinates instead) |
| `AUTO_REFRESH` | Set to `0` to turn off the hourly refresh |

Then:

```bash
uv run python -m alembic upgrade head
uv run python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. On Windows, `scripts/start.bat` starts PostgreSQL, applies migrations and opens the browser. Detailed setup (in Korean): `docs/setup.md`.

## Checks

```bash
uv run python scripts/check.py   # ruff, ruff format, mypy, pytest — same as CI
```

Tests run without network access or external accounts. External APIs are replaced with fakes at the adapter boundary, and recorded responses come from real calls or official documentation.

## Project layout

```
engine/            Pure logic, no DB/HTTP/web
  geo/             Lat/lon → KMA grid
  forecast/        KMA response parsing (short-range, mid-range)
  judgment/        Rule engine, Gongon Index
app/
  core/            Config, DB session, shared templates and styles
  features/        One folder per feature: router, service, repository, models, templates
    sites/  schedules/  forecasts/  judgments/
rules/             Criteria per work type (YAML, versioned)
migrations/        Alembic revisions
docs/              Plan, decisions, architecture, setup (Korean)
tests/
```

Dependencies only point one way: `app → engine`. Features call each other only through `service` and `schemas`. `tests/test_import_boundaries.py` enforces this.

## Documentation

All project documents are in Korean.

| Topic | File |
| --- | --- |
| Current task and handoff | `docs/handoff.md`, `docs/plan.md` |
| Decisions and their reasons | `docs/decisions.md` |
| Architecture and code rules | `docs/architecture.md` |
| UI text and design tokens | `docs/brand.md` |
| Sources and verification | `docs/references.md` |

## Disclaimer

Gongon is a decision-support tool. Verdicts compare forecasts with published criteria; they do not guarantee site safety. The final decision always rests with the person responsible on site.
