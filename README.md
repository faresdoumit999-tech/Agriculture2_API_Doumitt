# 🌱 DOUMITT Agricultural ERP SaaS

نظام ERP زراعي سحابي متعدد المستأجرين (Multi-tenant) لإدارة المشاريع الزراعية والبيوت البلاستيكية، الشغّيلة بالحصة، المستودع المركزي وجرد الصيدليات، المصاريف الموسمية واليومية بعملتين (USD / SYP)، وفواتير سوق الخضرة مع حساب تكلفة وربحية كل بيت بلاستيكي بدقة.

## Tech Stack

- Python 3.13 + FastAPI
- PostgreSQL 15 + SQLAlchemy 2.0 Async (`asyncpg`)
- Alembic Async Migrations
- Pydantic v2 + pydantic-settings
- JWT (`OAuth2PasswordBearer`) + bcrypt
- Redis + fastapi-cache2 + Celery
- slowapi Rate Limiting + Sentry
- Docker Multi-stage + docker-compose (db, redis, web, celery_worker)
- Vanilla JS RTL SPA inside `templates/index.html`

## Quick Start (Docker)

```bash
cp .env.example .env
# عدّل SECRET_KEY و POSTGRES_PASSWORD
docker compose up --build
```

- الواجهة: http://localhost:8000
- Swagger: http://localhost:8000/docs
- فحص الصحة: http://localhost:8000/health

`web` يشغّل `alembic upgrade head` ثم `uvicorn` تلقائياً. `db` و `redis` غير مكشوفين خارج الشبكة الداخلية.

## Local Development

```bash
python -m venv .venv
source .venv/Scripts/activate    # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env             # عدّل DATABASE_URL و REDIS_URL إلى localhost
alembic upgrade head
uvicorn main:app --reload
```

المتطلبات المحلية: PostgreSQL 15 و Redis 7 (أو استخدم `docker compose up db redis`).

### Celery

```bash
celery -A worker.celery_app worker --loglevel=info
```

## Tests

```bash
pytest -q
```

الاختبارات تعمل على `sqlite+aiosqlite` مستقل وتغطي:

1. التسجيل وتسجيل الدخول والملف الشخصي.
2. إنشاء مشروع (10 بيوت + شغّيل 20%).
3. شراء لتر دواء بالدولار وسحب `0.25` لتر مع التحقق من `0.75` المتبقي وإنشاء المصروف، ثم إعادة الكمية عند حذف المصروف.
4. فاتورة سوق خضرة والتحقق من الكوميسيون، خصم الفلين والسيارة، صافي الشغّيل، ربح المالك، ومؤشرات البيت الواحد.
5. عزل البيانات بين المستخدمين.

## Accounting Rules

### العملات المزدوجة

| الإدخال | النتيجة |
|---|---|
| `USD` + سعر صرف > 0 | `SYP = USD × rate` |
| `SYP` + سعر صرف > 0 | `USD = SYP ÷ rate` |
| `SYP` بدون سعر صرف | `USD = 0.0` |

### المستودع

- الشراء يحفظ الكمية الابتدائية والمتبقية.
- السحب الجزئي (`0.25`, `0.5`, ...) يتحقق من `remaining >= used`، ينقص الرصيد، وينشئ `ExpenseRecord` تلقائياً بتكلفة الكمية الدقيقة وسعر صرف الشراء.
- حذف المصروف المرتبط بسحب يعيد الكمية إلى المستودع (بحد أقصى الكمية الابتدائية).

### حساب الشغّيل داخل الفاتورة

```
total_gross          = Σ(net_weight × unit_price)
after_commission     = total_gross - commission - other_deductions
sharecropper_gross   = after_commission × profit_pct / 100
sharecropper_deduction = (polystyrene + vehicle_fuel) × expense_pct / 100
sharecropper_net     = sharecropper_gross - sharecropper_deduction
net_total            = after_commission - polystyrene - vehicle_fuel
owner_net_profit     = net_total - sharecropper_net
```

المصاريف المنفصلة التي عليها `enters_sharecropper_calc = true` تُخصم أيضاً من مستحقات الشغّيل في كشف حساب المشروع. الفلين والبنزين يدخلان تلقائياً، مع إمكانية تعديل النسبة لكل مصروف.

### ربح المشروع

```
owner_net_profit = net_sales - total_expenses - sharecropper_final_payout
```

حيث `sharecropper_final_payout` = إجمالي حصته − خصومات فواتير الفلين/السيارة − خصومات المصاريف المنفصلة.

### البيت البلاستيكي الواحد

```
cost_per_greenhouse    = total_expenses / greenhouse_count
revenue_per_greenhouse = net_sales / greenhouse_count
profit_per_greenhouse  = owner_net_profit / greenhouse_count
```

## Project Structure

```text
.
├── main.py                 # FastAPI app, cache lifespan, routers, SPA
├── config.py               # pydantic-settings (no hardcoded secrets)
├── database.py             # async engine + cloud URL normalisation
├── models.py               # 6 SQLAlchemy 2.0 tables
├── schemas.py              # Pydantic v2 contracts
├── auth.py                 # JWT, bcrypt, tenant helpers, limiter
├── exceptions.py           # unified JSON errors + Sentry capture
├── worker.py               # Celery heavy inventory export
├── services/               # currency, warehouse, sharecropper engines
├── routers/                # auth, projects, warehouse, expenses, invoices, reports
├── templates/index.html    # RTL single-page dashboard
├── alembic/                # async migrations
├── tests/                  # pytest + httpx + aiosqlite
├── Dockerfile              # multi-stage builder → runner
└── docker-compose.yml      # db, redis, web, celery_worker
```

## Security & Multi-tenancy

- كل استعلام مقيّد بـ `owner_id` للمستخدم الحالي.
- دور `admin` يستطيع قراءة/إدارة بيانات كل المستأجرين، ويُضبط يدوياً في قاعدة البيانات (`UPDATE users SET role='admin' WHERE username='...'`).
- كاش التقارير مفتاحه يتضمن هوية المستخدم لمنع تسريب النتائج بين الحسابات.
- CORS من `ALLOWED_ORIGINS`، وتسجيل الدخول محدود بـ `5/minute` افتراضياً.
- جميع الأخطاء تعود بصيغة `{"success": false, "error": {"code", "message", "details"}}`.

## Environment Variables

انظر `.env.example`. الأهم:

- `SECRET_KEY` (إلزامي، 16 حرفاً على الأقل)
- `DATABASE_URL` (Neon/Railway/Back4App تتحول تلقائياً إلى `postgresql+asyncpg://`)
- `REDIS_URL`
- `ALLOWED_ORIGINS`
- `CACHE_ENABLED`, `CACHE_TTL_SECONDS`
- `RATE_LIMIT_ENABLED`, `LOGIN_RATE_LIMIT`, `REPORT_RATE_LIMIT`
- `SENTRY_DSN` (اختياري)

## API Highlights

| Method | Path | Description |
|---|---|---|
| POST | `/api/register` | إنشاء حساب |
| POST | `/api/login` | JWT Token |
| GET | `/api/me` | بيانات المستخدم |
| DELETE | `/api/reset` | تصفير بيانات الحساب |
| POST/GET/PUT/DELETE | `/api/projects` | إدارة المشاريع والمواسم |
| POST/GET/PUT | `/api/warehouse/items` | المستودع |
| POST | `/api/warehouse/consume` | سحب جزئي + مصروف تلقائي |
| GET | `/api/warehouse/pharmacies-audit` | جرد الصيدليات |
| POST/GET/PUT/DELETE | `/api/expenses` | المصاريف |
| POST/GET/PUT/DELETE | `/api/invoices` | فواتير السوق |
| GET | `/api/reports/project/{id}/full-audit` | التقرير الشامل (cached) |
| GET | `/api/reports/global-summary` | لوحة القيادة العامة |
| GET | `/api/crops/{name}/history` | تاريخ مبيعات محصول |
| POST | `/api/reports/heavy-export` | مهمة Celery للجرد الشامل |
