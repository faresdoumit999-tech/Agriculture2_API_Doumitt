# 🚜 DOUMITT — Agricultural Invoicing & Expense Management SaaS

A multi-tenant SaaS backend that helps Syrian farmers track crop invoices, expenses, and profitability — with full data isolation per user, async PostgreSQL access, and Redis-backed caching.

[![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-async-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-caching-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Pytest](https://img.shields.io/badge/tested%20with-pytest-0A9EDC?logo=pytest&logoColor=white)](https://pytest.org/)

**Live demo:** _add your current deployment URL here_
**API docs (Swagger):** `<live-url>/docs`

---

## Why this project exists

Farmers in Syria track invoices and expenses on paper or in scattered spreadsheets, making it hard to know — at a glance — whether a crop season was actually profitable. DOUMITT gives each farmer an isolated account to log invoices and expenses and get an instant income/expense/profit summary, without needing any accounting background.

## Key Features

- **Multi-tenant data isolation** — every farmer has an independent account; no user can see another user's invoices or expenses, enforced at the query level via JWT-derived `owner_id`.
- **JWT authentication** — stateless auth with bcrypt-hashed passwords (`passlib`).
- **Invoice & expense tracking** — single and bulk invoice creation, with per-crop line items (`InvoiceItem`).
- **Crop analytics** — per-crop history and yearly filtering, plus aggregate income/expense/profit summaries.
- **Redis-backed response caching** — the summary endpoint is cached (`fastapi-cache2`) to avoid recomputing aggregates on every request.
- **Centralized error handling** — a custom exception hierarchy (`DoumittBaseException` and subclasses) maps domain errors to consistent JSON responses instead of ad-hoc `HTTPException` calls scattered across routes.
- **Fully async data layer** — SQLAlchemy 2.x async engine/session end-to-end, with `selectinload` used explicitly to avoid N+1 queries on invoice items.
- **Dockerized local environment** — `docker-compose` spins up the API, PostgreSQL, and Redis together with live reload.

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI (async) |
| Database | PostgreSQL via `asyncpg` |
| ORM | SQLAlchemy 2.x (async) |
| Migrations | Alembic |
| Caching | Redis (`fastapi-cache2`) |
| Auth | JWT (`python-jose`) + `passlib`/`bcrypt` |
| Testing | Pytest + `pytest-asyncio` + `httpx` (SQLite in-memory for test isolation) |
| Containerization | Docker / docker-compose |
| CI | GitHub Actions |

## Architecture notes

- **Config management**: all secrets and connection strings are loaded through `pydantic-settings` from environment variables — nothing is hardcoded.
- **Auth flow**: `POST /api/register` → `POST /api/login` returns a JWT (7-day expiry) → every protected route resolves the current user via `Depends(get_current_user)`, which decodes and verifies the token before touching the database.
- **Error handling**: domain errors (e.g. `UserAlreadyExistsError`) are raised as typed exceptions and caught by a single FastAPI exception handler, so every error response has the same shape: `{ "error_type", "message", "path" }`.
- **N+1 prevention**: `Invoice.items` uses `lazy="selectin"` at the model level, and endpoints also use `selectinload` explicitly — so fetching a list of invoices with their line items takes a small, fixed number of queries regardless of list size.

## Getting Started (local, via Docker)

```bash
git clone https://github.com/faresdoumit999-tech/Agriculture2_API_Doumitt.git
cd Agriculture2_API_Doumitt
cp .env.example .env   # fill in your own values
docker-compose up --build
```

The API will be available at `http://localhost:8000`, with interactive docs at `http://localhost:8000/docs`.

### Running migrations

```bash
docker-compose exec web alembic upgrade head
```

### Running tests

```bash
pip install -r requirements.txt
pytest
```

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/register` | Create a new farmer account |
| `POST` | `/api/login` | Authenticate and receive a JWT |
| `POST` | `/api/invoices` | Create a single invoice with line items |
| `POST` | `/api/invoices/bulk` | Create multiple invoices in one transaction |
| `GET` | `/api/invoices` | List invoices (paginated) for the current user |
| `POST` | `/api/expenses` | Log an expense |
| `GET` | `/api/summary` | Cached income/expense/profit summary |
| `GET` | `/api/reports/summary` | Filterable report (by date range / crop) |
| `GET` | `/api/crops` | Distinct crop names for the current user |
| `GET` | `/api/crops/{crop_name}/history` | Full history for one crop |
| `DELETE` | `/api/reset` | Wipe the current user's data |

Full interactive documentation is auto-generated by FastAPI at `/docs`.

## Roadmap

A few things I'm actively improving as I deepen my backend fundamentals:

- [ ] Wire up refresh tokens and role-based access control (the `role` field already exists on `User`, not yet enforced)
- [ ] Re-enable and finish the test step in the CI pipeline
- [ ] Add structured logging instead of raw SQL echo
- [ ] Add rate limiting on `/api/login` and `/api/register`
- [ ] Cache invalidation on invoice/expense writes (currently relies on a 60s TTL only)

## Author

**Fares Doumit** — Telecom engineering student & backend developer, building production-style backend systems from Syria.
[GitHub](https://github.com/faresdoumit999-tech) · _add your LinkedIn link here_
