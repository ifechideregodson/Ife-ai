# My AI Mobile v8.0

FastAPI personal AI project for Android/Termux with chat history, voice input, text-to-speech, PWA support and image understanding.

## Android / Termux

pkg update
pkg install python
python -m pip install -r requirements.txt
cp .env.example .env
nano .env
uvicorn app.main:app --host 0.0.0.0 --port 8000

Open http://127.0.0.1:8000.

## Environment

OPENAI_API_KEY=your_secret_key
OPENAI_MODEL=gpt-5
ASSISTANT_NAME=My AI
AI_SYSTEM_PROMPT=You are My AI, a helpful personal assistant. Be clear and friendly.

Keep your API key only in .env and never put it in frontend JavaScript.

## API endpoints

POST /chat - AI chat
POST /api/image - image understanding
GET /api/status - connection status
GET /api/history - chat history
POST /api/clear - clear history
GET /api/export - export chat
GET /api/settings - settings
GET /api/health - health
