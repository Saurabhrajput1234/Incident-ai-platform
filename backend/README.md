# Incident AI Platform

AI-powered incident management platform built with FastAPI.

## Setup

### Prerequisites
- Python 3.11+

### Installation

1. Create virtual environment:
```bash
cd backend
python -m venv venv
```

2. Activate virtual environment:
```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -e .
```

4. Create environment file:
```bash
cp .env.example .env
```

### Running the Application

```bash
uvicorn app.main:app --reload
```

The API will be available at:
- API: http://localhost:8000
- Health Check: http://localhost:8000/v1/health
- API Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
backend/
├── app/
│   ├── api/              # API endpoints
│   ├── core/             # Core configuration
│   ├── modules/          # Business modules
│   └── main.py           # Application entry point
├── pyproject.toml        # Dependencies
└── .env.example          # Environment template
```

## Development

### Health Check
```bash
curl http://localhost:8000/v1/health
```

Response:
```json
{"status": "healthy"}
```
