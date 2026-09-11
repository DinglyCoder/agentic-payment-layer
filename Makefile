.PHONY: install test format dev-backend dev-frontend

install:
	cd backend && uv sync
	cd contracts && npm install
	cd frontend && npm install

test:
	cd backend && uv run pytest
	cd contracts && npm test
	cd frontend && npm run build

format:
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd contracts && npm run check
	cd frontend && npm run lint

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload

dev-frontend:
	cd frontend && npm run dev
