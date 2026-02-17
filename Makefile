.PHONY: dev dev-build logs logs-engine logs-backend logs-mt5 db-migrate db-rollback db-seed db-shell test test-cov deploy stop restart restart-all version backup clean status

# ─── DEVELOPMENT ───
dev:
	docker compose up

dev-build:
	docker compose up --build

dev-detach:
	docker compose up -d --build

logs:
	docker compose logs -f

logs-engine:
	docker compose logs -f jsr-engine

logs-backend:
	docker compose logs -f jsr-backend

logs-mt5:
	docker compose logs -f jsr-mt5

# ─── DATABASE ───
db-migrate:
	docker compose exec jsr-backend alembic upgrade head

db-rollback:
	docker compose exec jsr-backend alembic downgrade -1

db-seed:
	docker compose exec jsr-backend python -m app.db.seed_runner

db-shell:
	docker compose exec jsr-postgres psql -U $${DB_USER:-postgres} -d jsr_hydra

# ─── TESTING ───
test:
	docker compose exec jsr-backend pytest -v

test-cov:
	docker compose exec jsr-backend pytest --cov=app --cov-report=term-missing

test-local:
	PYTHONPATH=backend python3 -m pytest backend/tests/ -v

# ─── PRODUCTION ───
deploy:
	docker compose up -d --build
	docker compose exec jsr-backend alembic upgrade head
	@echo "Deployed successfully"

stop:
	docker compose down

restart:
	docker compose restart jsr-engine jsr-backend

restart-all:
	docker compose down && docker compose up -d

# ─── MAINTENANCE ───
backup:
	@mkdir -p backups
	docker compose exec -T jsr-postgres pg_dump -U $${DB_USER:-postgres} jsr_hydra | gzip > backups/jsr_hydra_$$(date +%Y%m%d_%H%M%S).sql.gz
	@echo "Backup saved to backups/"

clean:
	docker compose down -v
	docker system prune -f

version:
	@cat version.json | python3 -m json.tool

status:
	@docker compose ps
	@echo ""
	@cat version.json | python3 -c "import sys,json; v=json.load(sys.stdin); print(f'  v{v[\"version\"]} {v[\"codename\"]}')"
