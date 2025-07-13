# Warehouse Management System - Makefile
.PHONY: help build up down logs clean migrate collectstatic shell test lint format

# Default target
help:
	@echo "Available commands:"
	@echo "  build          - Build all Docker containers"
	@echo "  up             - Start all services"
	@echo "  down           - Stop all services"
	@echo "  logs           - View logs from all services"
	@echo "  logs-backend   - View backend logs only"
	@echo "  logs-db        - View database logs only"
	@echo "  clean          - Remove all containers and volumes"
	@echo "  migrate        - Run Django migrations"
	@echo "  makemigrations - Create new Django migrations"
	@echo "  collectstatic  - Collect static files"
	@echo "  shell          - Access Django shell"
	@echo "  dbshell        - Access PostgreSQL shell"
	@echo "  test           - Run Django tests"
	@echo "  lint           - Run code linting"
	@echo "  format         - Format code"
	@echo "  setup          - Initial setup (build + migrate + collectstatic)"

# Build containers
build:
	docker compose build

# Start services
up:
	docker compose up -d

# Stop services
down:
	docker compose down

# View logs
logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-db:
	docker compose logs -f db

# Clean everything
clean:
	docker compose down -v
	docker system prune -f

# Django management commands
migrate:
	@echo "Starting database and running migrations..."
	docker compose up -d db
	@echo "Waiting for database to be ready..."
	@sleep 10
	docker compose run --rm backend uv run python manage.py migrate

makemigrations:
	@echo "Creating new Django migrations..."
	docker compose run --rm backend uv run python manage.py makemigrations

collectstatic:
	docker compose run --rm backend uv run python manage.py collectstatic --noinput

# Development tools
shell:
	docker compose run --rm backend uv run python manage.py shell

dbshell:
	docker compose exec db psql -U warehouse_user -d warehouse

# Testing and code quality
test:
	@echo "Starting database for tests..."
	docker compose up -d db
	@sleep 5
	docker compose run --rm -e DJANGO_SETTINGS_MODULE=warehouse.settings backend uv run pytest

test-verbose:
	@echo "Starting database for tests..."
	docker compose up -d db
	@sleep 5
	docker compose run --rm -e DJANGO_SETTINGS_MODULE=warehouse.settings backend uv run pytest -v

test-coverage:
	@echo "Starting database for tests..."
	docker compose up -d db
	@sleep 5
	docker compose run --rm -e DJANGO_SETTINGS_MODULE=warehouse.settings backend uv run pytest --cov=. --cov-report=html

test-auth:
	@echo "Starting database for tests..."
	docker compose up -d db
	@sleep 5
	docker compose run --rm -e DJANGO_SETTINGS_MODULE=warehouse.settings backend uv run pytest -m auth

test-inventory:
	@echo "Starting database for tests..."
	docker compose up -d db
	@sleep 5
	docker compose run --rm -e DJANGO_SETTINGS_MODULE=warehouse.settings backend uv run pytest -m inventory

test-api:
	@echo "Starting database for tests..."
	docker compose up -d db
	@sleep 5
	docker compose run --rm -e DJANGO_SETTINGS_MODULE=warehouse.settings backend uv run pytest -m api

test-unit:
	@echo "Starting database for tests..."
	docker compose up -d db
	@sleep 5
	docker compose run --rm -e DJANGO_SETTINGS_MODULE=warehouse.settings backend uv run pytest -m unit

lint:
	@echo "Running linting checks..."
	docker compose run --rm backend uv run ruff check .
	docker compose run --rm backend uv run mypy .

format:
	@echo "Formatting code..."
	docker compose run --rm backend uv run ruff format .
	docker compose run --rm backend uv run ruff check --fix .

# Initial setup
setup: build migrate collectstatic
	@echo "Setup complete! Run 'make up' to start all services."

# Database operations
db-reset:
	@echo "Resetting database..."
	docker compose down
	docker volume rm real-time-processing_postgres_data 2>/dev/null || true
	make migrate

# Development workflow
dev-start:
	@echo "Starting development environment..."
	docker compose up -d db redis kafka zookeeper
	@sleep 10
	make migrate
	@echo "Backend database ready. Start Django with: make dev-backend"

dev-backend:
	cd backend && uv run python manage.py runserver 0.0.0.0:8000

# Kafka operations
kafka-topics:
	docker compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

kafka-console-consumer:
	@echo "Starting Kafka console consumer for topic: $(TOPIC)"
	docker compose exec kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic $(TOPIC) --from-beginning

# Monitoring
monitor:
	@echo "Access points:"
	@echo "  - Backend API: http://localhost:8000"
	@echo "  - Frontend:    http://localhost:3000"
	@echo "  - Kafka UI:    http://localhost:8080"
	@echo "  - Grafana:     http://localhost:3001 (admin/admin)"
	@echo "  - InfluxDB:    http://localhost:8086"
	@echo "  - Elasticsearch: http://localhost:9200"
	@echo "  - Log Viewer:  http://localhost:5000"

# Health check
health:
	@echo "Checking service health..."
	@docker compose ps