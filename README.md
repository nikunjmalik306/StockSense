# StockSense

StockSense is a full-stack inventory intelligence and risk management application. It tracks inventory in real-time, calculates product risk scores (stockouts, expirations, overstock), and uses machine learning to forecast future demand. 

## Features

- **Authentication & Security:** Secure JWT-based authentication with role-based access control (RBAC).
- **Core Inventory Management:** Full CRUD capabilities for products, categories, and suppliers.
- **Transactions:** Log stock-in and stock-out events, maintaining a complete transactional history and FIFO accounting logic.
- **Dashboard & KPIs:** Overview of inventory health, recent transactions, and key metrics.
- **Risk Analysis Engine:** Calculates a 0-100 composite risk score for products based on stockout probability, expiry risk, overstock, and demand velocity.
- **Demand Forecasting:** Uses a global XGBoost machine learning model trained on historical data to predict product demand over the next 7-30 days, falling back to a 7-day Simple Moving Average (SMA-7) for products with limited history.

## Tech Stack

**Frontend:**
- React 18 (TypeScript)
- Vite
- Tailwind CSS v3
- React Router v6
- React Query (TanStack Query)
- React Hook Form + Zod (Validation)
- Recharts (Data Visualization)

**Backend:**
- Python 3.11
- FastAPI
- SQLAlchemy 2.0 (Async)
- PostgreSQL 16 (Primary Database)
- Alembic (Database Migrations)

**Machine Learning:**
- XGBoost & Scikit-Learn
- Pandas & NumPy

*(Note: Redis is included in the infrastructure configuration for future caching/rate-limiting but is not currently actively utilized in the business logic.)*

## Architecture

```text
React Frontend (Vite)
      ↓ (REST API / JSON)
FastAPI Backend (Uvicorn / Python)
      ↓ (AsyncPG)
PostgreSQL Database
      ↓ 
ML Engine (XGBoost / Pandas)
```

## Application Features

- **Dashboard:** Operational overview of stock value, recent transactions, and high-risk alerts.
- **Inventory & Products:** Manage stock configurations, safety stock, reorder points, and lead times.
- **Transactions:** Detailed ledger of all stock movements.
- **Categories:** Group and organize inventory items.
- **Suppliers:** Manage vendor details and lead times (with audit logging).
- **Inventory Risk:** A dedicated view ranking products by their composite vulnerability score.
- **Demand Forecast:** Visualize historical trends against ML-generated future predictions.

## Risk Analysis Engine

The application employs a deterministic risk engine that calculates a 0-100 score based on four weighted factors:
1. **Stockout Risk:** Evaluates current stock against daily demand and supplier lead times.
2. **Expiry Risk:** Identifies soon-to-expire batches and estimates potential financial waste.
3. **Overstock Risk:** Penalizes excess inventory tying up capital.
4. **Demand Velocity:** Adjusts risk based on accelerating or decelerating consumption trends.

*Operational Escalations:* The engine enforces minimum risk floors (e.g., 75+ "CRITICAL" for zero stock, 50+ "HIGH" for imminent stockouts before supplier delivery) to ensure operational urgency overrides pure mathematical weighting.

## Role-Based Access Control (RBAC)

The system enforces three distinct access levels:

| Role      | Permissions                                                                                     |
|-----------|-------------------------------------------------------------------------------------------------|
| **ADMIN** | Full access. Can create, read, update, and violently delete records (e.g., products, suppliers). |
| **MANAGER**| Can create and edit products, configure inventory, and manually trigger ML model retraining. Cannot delete records. |
| **STAFF** | Read-only access to most configurations. Permitted to execute standard operational transactions (stock-in, stock-out). |

## Local Development

### Prerequisites
- Docker & Docker Compose
- Node.js (v18+)
- Python 3.10+

### Environment Setup
1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
2. Update the `.env` file with appropriate secure values.

### Starting Services via Docker (Recommended for Backend/DB)
Start PostgreSQL, Redis, and the FastAPI application:
```bash
docker compose up -d
```

Run database migrations and seed initial development data:
```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python seed/seed.py
```

### Starting the Frontend
To run the React application locally with Hot Module Replacement (HMR):
```bash
cd frontend
npm install
npm run dev
```
The application will be accessible at `http://localhost:5173`.

## API Documentation
When running the backend locally, the interactive FastAPI Swagger documentation is available at `http://localhost:8000/docs`.

## Testing

**Backend Tests:**
Ensure you have the virtual environment configured and dependencies installed:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```
*(The test suite currently contains over 180 tests validating backend logic and ML configurations).*

## Production Build & Deployment
- **Frontend (Vercel/Netlify):** Execute `npm run build` to output the optimized static bundle to `dist/`. Remember to set the `VITE_API_BASE_URL` environment variable.
- **Backend (Render/Fly.io):** Use the command `uvicorn app.main:app --host 0.0.0.0 --port $PORT` after installing `requirements.txt`. Ensure `CORS_ORIGINS` is configured securely.

## Security Notes
- JWT secrets must be changed in production.
- Default PostgreSQL passwords must be updated.
- All dependencies are isolated and `.gitignore` correctly prevents the accidental tracking of credentials, virtual environments, and ML model binaries.

## Author

Nikunj Malik  
[GitHub Profile](https://github.com/nikunjmalik306)
