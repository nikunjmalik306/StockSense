# StockSense

StockSense is a full-stack inventory intelligence platform that combines real-time inventory management with risk analysis and demand forecasting. It helps users prevent stockouts, identify high-risk products, and make data-driven inventory decisions.

## Features

- **Authentication:** Secure login and user session management via JWT.
- **Inventory Management:** Full CRUD operations for products, categories, and suppliers.
- **Transactions:** Track stock-in and stock-out events with complete history.
- **Dashboard & KPIs:** Real-time visibility into inventory health and business metrics.
- **Risk Analysis:** Identify high-risk products and analyze inventory vulnerability.
- **Demand Forecasting:** Machine Learning-based predictions for future product demand.

## Tech Stack

**Frontend:**
- React
- TypeScript
- Vite
- Tailwind CSS

**Backend:**
- FastAPI
- Python
- SQLAlchemy
- REST APIs

**Database:**
- PostgreSQL
- Redis

**Machine Learning:**
- Scikit-Learn
- XGBoost
- Pandas & NumPy

## Architecture

```text
React Frontend
      ↓
  REST API
      ↓
FastAPI Backend
      ↓
  PostgreSQL (Database) / Redis (Cache)
      ↓
Machine Learning (Scikit-Learn/XGBoost)
```

## Project Structure

```text
StockSense/
├── backend/          # FastAPI application, SQLAlchemy models, Alembic migrations, ML scripts
├── frontend/         # React, Vite, Tailwind CSS, TypeScript
├── docker-compose.yml # Local development orchestration
└── .env.example      # Environment variables template
```

## Screens & Functionality

- **Login:** Secure authentication entry point.
- **Dashboard:** Overview of inventory health, recent transactions, and key performance indicators.
- **Inventory & Products:** Manage stock levels, view product details, and monitor thresholds.
- **Transactions:** Log stock movements and view historical data.
- **Categories:** Organize inventory by logical groupings.
- **Suppliers:** Manage vendor relationships and details.
- **Risk Analysis:** View risk scores and identify vulnerable products.
- **Demand Forecasting:** Access ML-generated predictions for future demand.

## Local Development

### Prerequisites
- Docker & Docker Compose
- Node.js
- Python 3.10+

### Environment Setup
1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Update the `.env` file with appropriate values.

### Starting Services via Docker (Recommended for Backend/DB)
Start the PostgreSQL database, Redis, and the FastAPI backend:
```bash
docker compose up -d
```

To run database migrations and seed initial data:
```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python seed/seed.py
```

### Starting the Frontend
The frontend is typically run locally for faster development feedback:
```bash
cd frontend
npm install
npm run dev
```
The frontend will be available at `http://localhost:5173`.

## Environment Variables
The application uses environment variables for configuration. See `.env.example` for the required variables. **Never commit actual credentials to the repository.**

## API
The backend exposes REST APIs using FastAPI. Interactive API documentation (Swagger UI) is available at `http://localhost:8000/docs` when the backend is running.

## Testing

**Backend Tests:**
Ensure you are in the `backend` directory and have dependencies installed:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

## Production Deployment
The application is structured to be deployed using modern PaaS providers.
- **Backend:** Ready for deployment (e.g., Render, Fly.io) using `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- **Frontend:** Can be deployed to static hosting providers (e.g., Vercel, Netlify) via `npm run build`. 
Ensure `VITE_API_BASE_URL` is configured to point to the production backend URL.
- **Database:** Requires a managed PostgreSQL instance and a Redis instance.

## Future Improvements

- Integration with physical barcode scanners for faster stock-in/out.
- Multi-tenant support for multiple warehouses.

## Author

Dakshayani Sharma
