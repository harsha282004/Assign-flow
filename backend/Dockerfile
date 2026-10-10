FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install runtime + dev (pytest, ruff) dependencies declared in pyproject.toml (cached unless it changes).
COPY pyproject.toml ./
RUN python -c "import tomllib;p=tomllib.load(open('pyproject.toml','rb'))['project'];print('\n'.join(p['dependencies']+p['optional-dependencies']['dev']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

RUN useradd --system --uid 10001 --no-create-home appuser

COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
COPY tests ./tests
# Normalise CRLF line endings (Windows checkouts) and set the exec bit inside the image.
COPY entrypoint.sh ./entrypoint.sh
RUN sed -i 's/\r$//' entrypoint.sh && chmod 755 entrypoint.sh

USER appuser
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
