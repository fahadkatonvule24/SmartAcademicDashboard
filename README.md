# IUIU Kampala Campus Academic ERP System

An academic ERP portal for IUIU Kampala Campus. The system provides separate lecturer and student workspaces for course units, lecture sessions, resource access, quiz preparation, feedback, timetable planning, and mother-tongue translation support.

## Main App

Run the integrated ERP dashboard:

```bash
uvicorn main:app --reload --port 8002
```

Open:

```text
http://127.0.0.1:8002/
```

Local access accounts:

```text
Lecturer: lecturer / demo123
Student:  student  / demo123
```

## Features

- IUIU Kampala Campus branded ERP login and dashboard shell.
- Lecturer workspace for virtual lecturer rooms, lecture sessions, file uploads, quiz preparation, and student feedback review.
- Student workspace for registered course units, lecture resources, translated PDFs, quizzes, study planning, timetable planning, and course support.
- Profile and nationality-based language selection with manual language override.
- Course glossary protection for terms such as ERP, quiz, dashboard, and course-specific terminology.
- Translation cache and local audit logs.
- JSON-backed local persistence for a simple deployment and defense environment.
- FastAPI endpoints with Swagger documentation at `/docs`.

## Project Structure

- `main.py`: deployment entry point for the integrated ERP.
- `iuiu_dashboard/`: main ERP API and service layer.
- `static_dashboard/`: main lecturer/student browser interface.
- `iuiu_nlp/`: translation service, language mapping, glossary, cache, and providers.
- `static/`: standalone translation interface.
- `iuiu_course_assistant/`: resource indexing and course-answer service.
- `static_course_assistant/`: standalone course assistant interface.
- `data/`: local JSON storage and uploaded resource metadata.
- `tests/`: automated tests for the services and API routes.
- `DEPLOYMENT.md`: deployment steps for Docker and hosted platforms.

## Installation

```bash
python -m pip install -r requirements.txt
```

Run tests:

```bash
python -m pytest -q
```

## Deployment

The deployment entry point is:

```text
main:app
```

Use this start command on Render, Railway, Heroku-style platforms, or a VPS:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

For Docker:

```bash
docker build -t iuiu-kampala-erp .
docker run --env-file .env -p 8000:8000 iuiu-kampala-erp
```

Health check:

```text
/health
```

Environment variables are documented in `.env.example`.

## Standalone Modules

Translation service:

```bash
uvicorn iuiu_nlp.api:app --reload --port 8000
```

Course assistant:

```bash
uvicorn iuiu_course_assistant.api:app --reload --port 8001
```

Integrated ERP:

```bash
uvicorn main:app --reload --port 8002
```

## Data Storage Note

The project uses local JSON files under `data/`. For hosted deployment, attach persistent storage or configure the data paths in the environment so profiles, resources, cache files, and uploads survive restarts.

## Language Handling Note

Nationality is used as the default language-resolution rule, but the system also supports preferred-language profiles and per-request manual overrides. This keeps the portal flexible for students whose preferred academic language differs from the nationality mapping.
