# My AI v11

A personal AI assistant built with FastAPI for Android/Termux.

## v11 features
- Account registration and login
- Private sessions using secure HTTP-only cookies
- Multiple conversations/chats
- Automatic chat titles
- Long-term memory per account
- PDF/TXT/MD/CSV document upload and reading
- Optional web search through the OpenAI Responses API
- Image understanding
- Voice input and text-to-speech
- Mobile/PWA interface
- Chat export

## Android / Termux

```bash
pkg update
pkg install python
python -m pip install -r requirements.txt
cp .env.example .env
nano .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open `http://127.0.0.1:8000` on your phone.

## Environment

```
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.6-luna
ASSISTANT_NAME=My AI
AI_SYSTEM_PROMPT=You are My AI, a helpful personal assistant. Be clear and friendly.
```

Keep the API key only in `.env`. Never put it in frontend JavaScript or commit it to GitHub.

## Main API
- POST `/api/auth/register`
- POST `/api/auth/login`
- POST `/api/auth/logout`
- GET `/api/auth/me`
- GET/POST/DELETE `/api/conversations`
- GET `/api/history`
- POST `/chat`
- GET/POST/DELETE `/api/memory`
- GET/POST/DELETE `/api/documents`
- POST `/api/image`
- GET `/api/export`
- GET `/api/status`
- GET `/api/health`

The default model is GPT-5.6 Luna. OpenAI's current model documentation lists GPT-5.6 Luna as supporting text/image input and the Responses API, with web search and file search available among the supported tools. 
