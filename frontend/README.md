# Budgeted Research Agent Console

React + TypeScript research console for the FastAPI backend. It creates Fixed or
Adaptive runs, streams actions over SSE, displays live budget usage, inspects
validated evidence and grounded reports, and can cancel active work.

## Development

Start the backend first from `backend/`:

```bash
uv run bra serve --reload
```

Then install and start the frontend from this directory:

```bash
npm install
npm run dev
```

Open `http://localhost:5173`. The console uses
`http://127.0.0.1:8000/api/v1` by default. Override it with:

```bash
cp .env.example .env
```

## Quality checks

```bash
npm run test
npm run build
```
