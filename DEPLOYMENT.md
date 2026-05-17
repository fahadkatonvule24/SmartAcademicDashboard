# Deployment

## Application Entry Point

Use the integrated ERP app:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

`main.py` imports `iuiu_dashboard.api:app`, so the deployment exposes the complete IUIU Kampala Campus ERP dashboard.

## Environment

Copy `.env.example` to `.env` for local configuration. On a hosting platform, set the same values in the platform environment settings.

Important variables:

- `PORT`: port assigned by the hosting platform.
- `TRANSLATION_PROVIDER`: use `auto` for the normal provider selection or `demo` for offline testing.
- `DATA_DIR`: persistent path for translation profiles, glossary, cache, and logs.
- `COURSE_ASSISTANT_DATA_DIR`: persistent path for course-resource metadata.
- `COURSE_ASSISTANT_UPLOAD_DIR`: persistent path for uploaded lecture resources.

Use persistent storage for the `data/` paths when deploying to a platform with an ephemeral filesystem.

## Docker

Build:

```bash
docker build -t iuiu-kampala-erp .
```

Run:

```bash
docker run --env-file .env -p 8000:8000 iuiu-kampala-erp
```

Open:

```text
http://127.0.0.1:8000/
```

## Platform Deployment

For Render, Railway, Heroku-style platforms, use:

```text
Build command: pip install -r requirements.txt
Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
```

Health check:

```text
/health
```

## Pre-Deployment Check

Run:

```bash
python -m pytest -q
uvicorn main:app --host 127.0.0.1 --port 8000
```

Then check:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/
```
