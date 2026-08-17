# StockSense

StockSense is a full-stack inventory intelligence platform for managing products, monitoring stock movements, identifying inventory risk, and forecasting future demand.

It combines inventory management with an explainable risk-scoring system and machine-learning-based demand forecasting to help users identify potential stockouts, inventory vulnerabilities, and replenishment requirements.

## Key Features

### Authentication & Role-Based Access
- JWT-based authentication and protected routes
- Role-based access control for:
  - **Admin** — full access, including record deletion
  - **Manager** — inventory management, stock operations, and ML model retraining
  - **Staff** — operational inventory access and stock transactions

### Inventory Management
- Product CRUD operations
- Category management
- Supplier management
- Current stock monitoring
- Inventory value tracking
- Stock-in and stock-out operations
- FIFO-based stock allocation
- Inventory threshold monitoring

### Transaction Management
- Stock-in and stock-out history
- Transaction quantities and timestamps
- User attribution
- Inventory movement tracking

### Inventory Risk Analysis
StockSense calculates an explainable risk score from 0–100 using four weighted factors:

| Risk Factor | Weight |
|-------------|--------|
| Stockout Risk | 40% |
| Expiry Risk | 35% |
| Overstock Risk | 15% |
| Demand Velocity | 10% |

Products are classified into:
- LOW
- MEDIUM
- HIGH
- CRITICAL

The system also applies operational escalation rules for critical inventory situations:
- Zero stock is escalated to **CRITICAL**
- A projected stockout occurring before supplier lead time is escalated to at least **HIGH**

The risk analysis interface exposes the score, contributing factors, inventory metrics, and recommended actions.

### Demand Forecasting
The forecasting pipeline uses historical demand information to estimate future product demand.

The current implementation uses:
- XGBoost regression as the primary forecasting model
- Scikit-learn Random Forest as a fallback when required
- A 7-day Simple Moving Average baseline when insufficient historical data is available

Forecasts can be generated for future demand horizons and are presented through the analytics interface. The system also uses forecast information when generating inventory replenishment recommendations.

### Dashboard & Analytics
The dashboard provides an overview of:
- Total products
- Inventory value
- Products at risk
- Products approaching expiry
- Risk distribution
- High-risk products
- Recent inventory activity

## Tech Stack

### Frontend
- React 18
- TypeScript
- Vite
- Tailwind CSS
- React Router
- TanStack Query
- Axios
- Recharts
- React Hook Form
- Zod

### Backend
- Python 3.11
- FastAPI
- SQLAlchemy
- Alembic
- Pydantic
- JWT authentication
- Passlib / bcrypt
- REST APIs

### Database & Infrastructure
- PostgreSQL
- Docker
- Docker Compose

*(Note: Redis is included in the development configuration but is not currently used as a core caching or rate-limiting layer in the application.)*

### Machine Learning & Data Processing
- XGBoost
- Scikit-learn
- Pandas
- NumPy

## Architecture

```text
┌──────────────────────────────────┐
│          React Frontend          │
│ TypeScript · Vite · Tailwind CSS │
└────────────────┬─────────────────┘
                 │
                 │ REST API
                 ▼
┌──────────────────────────────────┐
│          FastAPI Backend         │
│ Python · SQLAlchemy · JWT Auth   │
└────────────────┬─────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
┌───────────────┐  ┌────────────────────┐
│  PostgreSQL   │  │ Risk Engine        │
│   Database    │  │ & Forecasting      │
└───────────────┘  │ XGBoost / ML       │
                   └────────────────────┘


## Project Structure

```text
StockSense/
│
├── backend/
│   ├── app/
│   │   ├── routers/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── ml/
│   ├── alembic/
│   ├── seed/
│   ├── tests/
│   ├── requirements.txt
│   └── requirements-dev.txt
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── routes/
│   │   ├── hooks/
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md


## Application Pages

- **Login:** JWT-based authentication entry point with protected application access.
- **Dashboard:** Provides a high-level view of inventory health and recent activity.
- **Inventory:** Displays current inventory levels and provides stock management operations.
- **Products:** Manage product records, inventory thresholds, and product information.
- **Categories:** Create, update, and manage inventory categories.
- **Suppliers:** Manage supplier records and supplier information.
- **Transactions:** View the historical record of stock movements and inventory transactions.
- **Risk Analysis:** Analyze product-level inventory risk, risk scores, contributing factors, and recommended actions.
- **Demand Forecast:** Select products and view future demand predictions, forecast trends, model information, and replenishment recommendations.

## Role-Based Access Control

| Capability | Admin | Manager | Staff |
|------------|-------|---------|-------|
| View inventory | ✓ | ✓ | ✓ |
| View products | ✓ | ✓ | ✓ |
| Create products | ✓ | ✓ | — |
| Update products | ✓ | ✓ | — |
| Delete products | ✓ | — | — |
| Manage categories | ✓ | ✓ | — |
| Manage suppliers | ✓ | ✓ | — |
| Stock-in / Stock-out | ✓ | ✓ | ✓ |
| View transactions | ✓ | ✓ | ✓ |
| Inventory risk analysis | ✓ | ✓ | ✓ |
| Trigger ML retraining | ✓ | ✓ | — |

## Local Development

### Prerequisites
- Docker Desktop
- Node.js
- Python 3.10+
- Git

### Environment Setup

Clone the repository:
```bash
git clone https://github.com/nikunjmalik306/StockSense.git
cd StockSense
Create the local environment file:

bash


cp .env.example .env
Update the environment variables with the appropriate local configuration.

Start Backend Services
bash


docker compose up -d
Run database migrations:

bash


docker compose exec backend alembic upgrade head
If seed data is required:

bash


docker compose exec backend python seed/seed.py
The backend API runs at: http://localhost:8000
FastAPI Swagger documentation: http://localhost:8000/docs
Start the Frontend
bash


cd frontend
npm install
npm run dev
The frontend runs at: http://localhost:5173

Environment Variables
The project uses environment variables for application configuration. Use .env.example as the template for local and deployment configuration.

The frontend uses:

text


VITE_API_BASE_URL
to configure the backend API endpoint.

Never commit:

.env
Database credentials
JWT secrets
API keys
Other production credentials
Testing
Backend:

bash


cd backend
pytest
Current verified result: 181 passed, 4 skipped

Frontend Type Checking:

bash


cd frontend
npx tsc --noEmit
Frontend Production Build:

bash


cd frontend
npm run build
API
The backend exposes REST APIs through FastAPI. Major API areas include:

Authentication
Products
Categories
Suppliers
Inventory
Transactions
Analytics
Risk Analysis
Demand Forecasting
ML model operations
Interactive API documentation is available at http://localhost:8000/docs when running locally.

Deployment
The application is structured as a separate frontend and backend application.

Frontend
The React/Vite frontend can be deployed using Vercel.

Build command: npm run build
Output directory: dist
Set VITE_API_BASE_URL=<production-backend-url> in the Vercel environment variables.
Backend
The FastAPI backend can be deployed using a Python web-service platform such as Render.

Production command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
The production backend requires a managed PostgreSQL database and the appropriate environment variables.
Security
JWT-based authentication
Protected API routes
Role-based authorization
Environment-based secret configuration
Database credentials excluded from version control
.env files excluded through .gitignore
Future Improvements
Barcode scanner integration
Multi-warehouse inventory management
Additional forecasting models
Forecast performance monitoring
Automated inventory reorder workflows
Expanded inventory analytics
Project Status
StockSense currently includes the core inventory management workflow, transaction processing, explainable inventory risk analysis, and demand forecasting functionality.

The application has been verified with:

181 backend tests passing
TypeScript compilation with 0 errors
Successful production frontend build
Author
Nikunj Malik

