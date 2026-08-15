# 🎵 NaijaSound AI — Backend

AI-powered Nigerian music generation backend. Users sign up, type a theme,
get multilingual lyrics (English + Igbo + Yoruba + Hausa), then a premium
vocal track. Tracks are uploaded to Cloudinary and playable from each
creator's dashboard — think **Spotify-style UI on top of AI music generation**.

Built with **FastAPI**, **SQLAlchemy (async)**, **JWT auth**, and
**Cloudinary** for audio storage.

---

## Architecture

```
┌────────────┐    POST /auth/register     ┌──────────────────┐
│  Frontend  │ ─────────────────────────▶ │  FastAPI backend │
│  (React /  │    POST /auth/login        │                  │
│   Vue)     │ ◀────── JWT token ──────── │  • auth router   │
└─────┬──────┘                            │  • songs router  │
      │                                   │  • users router  │
      │  POST /api/v1/songs               └─────┬────────────┘
      │  {title, theme, style, language_mix}      │
      │                                            ▼
      │                          ┌─────────────────────────────┐
      │                          │ AIService (httpx async)     │
      │                          │ 1. /lyrics  → multilingual  │
      │                          │ 2. /music   → vocal track   │
      │                          └──────────┬──────────────────┘
      │                                     ▼
      │                          ┌─────────────────────────────┐
      │                          │ Cloudinary (audio storage)  │
      │                          │ naijasound/tracks/user_X/   │
      │                          └──────────┬──────────────────┘
      │                                     ▼
      │   GET /api/v1/songs        ┌─────────────────────────────┐
      └────────────────────────────▶ SQLAlchemy → Postgres/SQLite│
              (stream audio_url)    └─────────────────────────────�
```

---

## Project layout

```
NaijaSound/
├── app/
│   ├── core/
│   │   ├── config.py         # pydantic-settings, .env loader
│   │   ├── database.py       # async engine, session, Base
│   │   └── security.py       # JWT, password hashing, auth deps
│   ├── models/
│   │   └── models.py         # User, Song (SQLAlchemy)
│   ├── schemas/
│   │   └── schemas.py        # Pydantic request/response models
│   ├── services/
│   │   ├── ai_service.py     # Lyrics + music generation client
│   │   └── cloudinary_service.py
│   ├── routers/
│   │   ├── auth.py           # /register, /login, /me
│   │   ├── users.py          # /me dashboard
│   │   └── songs.py          # generate / list / get / delete
│   └── main.py               # FastAPI app + lifespan
├── requirements.txt
├── .env.example
└── README.md
```

---

## Quick start

### 1. Clone & install

```bash
cd NaijaSound
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your real keys:
#   - SECRET_KEY              (openssl rand -hex 32)
#   - AI_API_BASE_URL + KEY   (Tempolor / ElevenLabs / etc.)
#   - CLOUDINARY_*            (from your Cloudinary dashboard)
#   - DATABASE_URL            (defaults to sqlite+aiosqlite for dev)
```

### 3. Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**:      http://localhost:8000/redoc
- **Health**:     http://localhost:8000/health

---

## API reference

All routes are prefixed with `/api/v1`. Auth is via `Authorization: Bearer <jwt>`.

### Auth

| Method | Path                  | Body                                  | Returns           |
|--------|-----------------------|---------------------------------------|-------------------|
| POST   | `/auth/register`      | `{email, username, password, full_name?}` | `UserRead`     |
| POST   | `/auth/login`         | `{email, password}`                   | `{access_token, token_type, expires_in}` |
| GET    | `/auth/me`            | —                                     | `UserRead`        |

### Users

| Method | Path                  | Body           | Returns              |
|--------|-----------------------|----------------|----------------------|
| GET    | `/users/me`           | —              | `UserRead`           |
| PATCH  | `/users/me`           | `UserUpdate`   | `UserRead`           |
| GET    | `/users/me/dashboard` | —              | `{user, credits_remaining, songs_count}` |

### Songs

| Method | Path                | Body                                       | Returns                |
|--------|---------------------|--------------------------------------------|------------------------|
| POST   | `/songs/lyrics`     | `{theme, language_mix?, style_hint?}`      | `{lyrics, credits_used}` |
| POST   | `/songs`            | `SongGenerateRequest`                      | `SongRead` (status=ready)|
| GET    | `/songs`            | query: `page, page_size, status`            | `SongListResponse`     |
| GET    | `/songs/{id}`       | —                                          | `SongRead`             |
| DELETE | `/songs/{id}`       | —                                          | 204                    |

---

## End-to-end example (curl)

```bash
# 1. Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"ada@naijasound.ai","username":"ada","password":"securepass123"}'

# 2. Login → grab the JWT
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ada@naijasound.ai","password":"securepass123"}' | jq -r .access_token)

# 3. Generate a song
curl -X POST http://localhost:8000/api/v1/songs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Lagos Nights",
    "theme":"a Lagos night drive with friends",
    "style":"afro-fusion",
    "language_mix":"English, Igbo, Yoruba, Hausa"
  }'

# Response includes audio_url (Cloudinary) — point a <audio> tag at it.

# 4. List dashboard
curl http://localhost:8000/api/v1/songs \
  -H "Authorization: Bearer $TOKEN"
```

---

## Credits & cost model

Each user starts with **10 free credits**. Costs:

| Action                                | Cost        |
|---------------------------------------|-------------|
| `POST /songs/lyrics`                  | 1 credit    |
| `POST /songs` (lyrics + track)        | 71 credits  |
| `POST /songs` (user-supplied lyrics)  | 70 credits  |

Wire a payment provider (Paystack / Stripe) into `POST /users/me/credits` to
top up — out of scope for the MVP but the field is already on the User model.

---

## Switching the AI provider

`app/services/ai_service.py` is intentionally thin. To swap Tempolor for
ElevenLabs / Suno / Replicate, change:

- `AI_API_BASE_URL` in `.env`
- The `model` field in `_post` payloads
- The endpoint paths (`/lyrics`, `/music`)

The two methods that matter: `generate_lyrics()` and `generate_song()`.
Everything else (credits, DB, Cloudinary) stays put.

---

## Production notes

- Replace `sqlite+aiosqlite` with `postgresql+asyncpg` in `DATABASE_URL`.
- Add Alembic migrations (`alembic init migrations`) — `init_db()` is fine
  for prototyping but tables shouldn't be created from `Base.metadata` in prod.
- Set a strong `SECRET_KEY` (≥32 random bytes) — never use the dev default.
- Front the FastAPI app with **nginx** + run **uvicorn** behind
  **gunicorn** (`gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4`).
- Add rate limiting (e.g. `slowapi`) on `/auth/login` and the song generation
  endpoints — generating a track is expensive.
- Cloudinary uploads use `resource_type="video"` because Cloudinary treats
  audio files under the video pipeline; the result is delivered as a streaming
  MP3 URL your `<audio>` tag can consume directly.

---

## License

MIT — go build something loud. 🇳🇬
