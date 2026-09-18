# Ife AI v13

Personal AI assistant built with FastAPI.

## What's new in v14
- Basic per-IP request rate limiting for chat, image and document endpoints
- Stronger username and password validation
- API key remains server-side and is never returned by the API

## What's new in v13
- PostgreSQL-ready cloud database with SQLAlchemy
- SQLite fallback for local Android/Termux use
- User accounts, sessions, chats, memories and documents
- OpenAI Responses API
- Web search toggle
- Image understanding
- PDF/TXT/MD/CSV uploads
- Render Blueprint with managed Postgres
- Secure session cookie option for HTTPS
- Health endpoint: /api/health

## Run on Android/Termux
```bash
pkg update
pkg install python
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Open http://127.0.0.1:8000.

For real AI, set OPENAI_API_KEY in your environment or .env. Never commit your key.

## Render
The included render.yaml creates the web service and a managed Postgres database. Render can wire the database connection into DATABASE_URL. Render documents that Blueprint database resources can expose a connectionString to a service, and that secrets should use sync: false rather than being hard-coded. 

After deploying, add your private OPENAI_API_KEY in the Render service Environment settings. Do not put the key in GitHub.

For a Render service and database in the same region, use the internal database connection supplied by the Blueprint.

## Important
Existing v12 SQLite data is not automatically migrated into the new cloud Postgres database. Keep the old chat.db as a backup before switching databases.
