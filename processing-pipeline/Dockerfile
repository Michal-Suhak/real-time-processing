FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Set work directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install only dependencies (not the local package)
RUN uv sync --frozen --no-dev --no-install-project

# Create logs directory
RUN mkdir -p logs

# Copy project
COPY . .

# Install the project in the virtual environment
RUN uv sync --frozen --no-dev

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose health check port
EXPOSE 8090

# Run the processing pipeline
CMD ["uv", "run", "python", "-m", "src.main"]