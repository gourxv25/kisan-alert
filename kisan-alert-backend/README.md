# Kisan Alert Backend

FastAPI backend service for the Kisan Alert farm monitoring and alert notification system.

## Project Structure

```text
kisan-alert-backend/
├── app/
│   ├── main.py            # FastAPI entry point
│   ├── config.py          # Configuration settings via pydantic-settings
│   ├── services/          # Business logic services (weather, soil, database, LLM advice, WhatsApp)
│   │   ├── weather.py
│   │   ├── soil.py
│   │   ├── advisor.py
│   │   ├── vision.py
│   │   ├── whatsapp.py
│   │   └── db.py
│   ├── models/            # Pydantic request/response validation schemas
│   └── routers/           # API router endpoints
│       ├── whatsapp_webhook.py
│       └── escalations.py
├── data/
│   └── village_defaults.json  # Village metadata and coordinate defaults
├── .env.example           # Environment variables template
├── requirements.txt       # Project python dependencies
└── README.md              # Project documentation
```

## Getting Started

### Prerequisites

- Python 3.10+
- `pip` (Python package installer)

### Setup

1. **Clone/Navigate to the backend folder**:
   ```bash
   cd kisan-alert-backend
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   ```
   Activate the virtual environment:
   - **Windows (Command Prompt)**:
     ```cmd
     venv\Scripts\activate.bat
     ```
   - **Windows (PowerShell)**:
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
   - **macOS/Linux**:
     ```bash
     source venv/bin/activate
     ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables**:
   Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

### Running Locally

Run the development server using `uvicorn`:

```bash
uvicorn app.main:app --reload
```

The API documentation will be available at:
- Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

### Verification

Check the health status of the application by querying the health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

Expected JSON response:
```json
{"status": "healthy"}
```
