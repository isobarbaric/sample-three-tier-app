FROM python:3.12-slim AS base
RUN pip install poetry
# don't need virtual environment since we're in a container
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false
WORKDIR /app
COPY pyproject.toml ./
RUN poetry install --no-root --only main
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
