# PPTGen

AI-powered PowerPoint generation chat application (FastAPI + LangGraph backend, React frontend).

## Prerequisites

- Python 3.11+
- Node 18+
- [Ollama](https://ollama.com/) running locally with the model pulled:
  ```
  ollama pull gemma3n:e4b
  ```

## Backend setup

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env   # edit as needed
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The dev server starts at `http://localhost:5173` and proxies `/api` requests to `:8000`.

## Environment variables

See `backend/.env.example` for all configuration options (Ollama base URL, model name, CORS origins, DB path).
