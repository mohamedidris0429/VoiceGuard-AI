# VoiceGuard AI - deployment guide

This guide covers a single-host deployment of the FastAPI backend and the Vite frontend.
Nothing here provisions paid services; every step is self-hosted.

## 1. Requirements

| component | version |
| --- | --- |
| Python | 3.11+ (3.12 tested) |
| Node.js | 18+ (20 recommended) |
| PostgreSQL | 14+ (18 tested) |
| Disk | ~1 GB (model ~378 MB + audio) |
| RAM | 2 GB minimum; ~1 GB resident with the model loaded |

## 2. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Environment (create `backend/.env`; never commit it):

```ini
ENVIRONMENT=production
LOG_LEVEL=INFO
SECRET_KEY=<64+ random chars>
DATABASE_URL=postgresql+psycopg://voiceguard:<password>@127.0.0.1:5432/voiceguard
CORS_ORIGINS=https://voiceguard.example.com
STORAGE_DIR=/var/lib/voiceguard/storage
MODEL_ID=Vansh180/deepfake-audio-wav2vec2
MODEL_CACHE_DIR=/var/lib/voiceguard/model-cache
MODEL_THREADS=4
MAX_UPLOAD_MB=20
MAX_AUDIO_SECONDS=60
```

Generate a key: `python -c "import secrets; print(secrets.token_urlsafe(64))"`.

Database and schema:

```bash
python -m alembic upgrade head      # applies 0001_initial and 0002_segments
python -m alembic current           # expect: 0002_segments (head)
```

Pre-download the model once (needs outbound network):

```bash
python -c "from app.ai.detector import get_detector; get_detector().status(probe=True)"
```

Then set `MODEL_OFFLINE=1` if the host should never reach the network.

Run:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

> **Single worker is required.** The rate limiter and live-analysis sessions are in-process.
> For multiple workers, move rate limiting to Redis and add sticky sessions (or run one
> worker per host).

### Service manager (Linux systemd example)

```ini
[Unit]
Description=VoiceGuard AI API
After=network.target postgresql.service

[Service]
WorkingDirectory=/opt/voiceguard/backend
EnvironmentFile=/opt/voiceguard/backend/.env
ExecStart=/opt/voiceguard/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
User=voiceguard

[Install]
WantedBy=multi-user.target
```

On Windows, use a Task Scheduler "At startup" action pointing at the same uvicorn command, or
run it under a service wrapper of your choice.

## 3. Frontend

```bash
cd frontend
npm ci
VITE_API_BASE_URL=https://voiceguard.example.com/api npm run build
```

Serve `frontend/dist/` with any static server. SPA routing needs a fallback to
`index.html` for unknown paths.

## 4. Reverse proxy (nginx example)

```nginx
server {
    listen 443 ssl;
    server_name voiceguard.example.com;
    client_max_body_size 25m;

    ssl_certificate     /etc/ssl/certs/voiceguard.crt;
    ssl_certificate_key /etc/ssl/private/voiceguard.key;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;   # CPU inference can take longer than the default 60 s
        proxy_send_timeout 180s;
    }

    location / {
        root /opt/voiceguard/frontend/dist;
        try_files $uri /index.html;
    }
}
```

Set `CORS_ORIGINS` to the exact public origin. CORS already permits `http://localhost:*` and
`http://127.0.0.1:*` for local development.

## 5. Health checks and logging

* `GET /api/health` → `{status, database, model_available, uptime_seconds}`.
* `GET /api/model/status?load=true` → loads and reports the checkpoint revision.
* Logs use the `voiceguard*` loggers; ship stdout to your log collector.
* The app purges stale `.part` uploads at startup and logs the removed count.

Monitoring suggestions: alert when `/api/health` is non-200 or `database != "connected"`,
and when `model_available` stays false after a preload attempt.

## 6. Database migrations

```bash
python -m alembic upgrade head       # forward
python -m alembic downgrade -1       # one step back (0002 -> 0001)
python -m alembic history            # review
```

Always back up before a downgrade. `0002_segments` is additive and reversible; no Phase 1
column is altered.

## 7. Backup and recovery

```bash
# database
pg_dump -Fc -h 127.0.0.1 -U voiceguard voiceguard > voiceguard-$(date +%F).dump
# audio files (opaque UUID names, one directory per user)
tar czf voiceguard-audio-$(date +%F).tar.gz -C /var/lib/voiceguard storage/audio
```

Restore:

```bash
pg_restore -d voiceguard --clean --if-exists voiceguard-2026-11-22.dump
tar xzf voiceguard-audio-2026-11-22.tar.gz -C /var/lib/voiceguard
```

Back up the database and `storage/audio` together: rows reference stored files, and audio
without its rows (or vice versa) is inconsistent.

## 8. Upgrade procedure

1. Back up database + audio.
2. Stop the API service.
3. `git pull` (or copy the release), `pip install -r requirements.txt`, `npm ci && npm run build`.
4. `python -m alembic upgrade head`.
5. Start the service and check `/api/health` + `/api/model/status`.
6. Run the test suite against a staging database if the release changed backend code.

Rollback: stop, restore the backup, `alembic downgrade <previous revision>`, start the previous
release.

## 9. Security checklist

* `SECRET_KEY` supplied by the environment, unique per deployment.
* TLS terminated at the proxy; no plain HTTP exposure.
* PostgreSQL reachable only from the app host; least-privilege role.
* `CORS_ORIGINS` exact; no wildcard.
* `storage/` outside the web root and not served by the proxy.
* Rotate database passwords and `SECRET_KEY` after any suspected exposure (rotating the JWT
  key invalidates all sessions).
* Keep the model cache read-only for the service account.

## 10. Manual steps that cannot be automated here

* Providing database credentials, domain and TLS certificates.
* Downloading the ~378 MB model checkpoint (or copying a prepared cache).
* Installing/running the service manager and configuring the proxy.
* Supplying a labelled corpus if you want measured detector metrics
  (`python scripts/evaluate_model.py --dataset … --output …`).
