FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN useradd --uid 10001 --create-home operator

COPY pyproject.toml README.md ./
COPY src src
RUN pip install .

USER 10001
EXPOSE 8080 9090
ENTRYPOINT ["kopf"]
CMD ["run", "--standalone", "--all-namespaces", "-m", "greenwindow.operator.handlers"]
