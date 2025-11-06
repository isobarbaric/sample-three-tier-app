FROM python:3.12-slim AS base

# TODO: use uv in the future?
RUN pip install poetry

# don't need virtual environment since we're in a container
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false
WORKDIR /app
COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-root
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
