# Quotes System

A simple quotes system built with FastAPI, SQLite, and Jinja2 templates. It supports registration, login, quote CRUD, search, likes, and collections. Packaged with Docker Compose and Nginx for one-command startup.

## Quick start

1. Build and start:

```bash
docker compose up -d
```

2. Open [http://localhost](http://localhost) in your browser.

## Services

- **web**: FastAPI app served by Uvicorn on port 8000 inside the container.
- **nginx**: Reverse proxy exposing port 80.

## Data persistence

SQLite database is stored at `./data/app.db` on the host. The folder is mounted into the web container so data survives restarts.

## Configuration

Environment variables (see `docker-compose.yml`):

- `DATABASE_URL`: defaults to `sqlite:////data/app.db`
- `SECRET_KEY`: session signing key
- `PAGE_SIZE`: optional pagination size (default 10)

## Development

Install dependencies locally:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Access at http://localhost:8000 (without Nginx).

## Features

- Cookie-based sessions with bcrypt-hashed passwords
- Public quote browsing and search (content/explanation LIKE, author/source filters)
- Quote CRUD for owners
- Like & collect toggles with personal lists
- Shareable quote pages with copy-link and QR code for WeChat
- Minimal, content-focused UI using Jinja2 templates
