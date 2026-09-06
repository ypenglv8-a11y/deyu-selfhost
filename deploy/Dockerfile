FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 deyu
COPY src ./src
RUN mkdir -p /app/data && chown deyu:deyu /app/data
USER deyu
ENV DEYU_DB=/app/data/deyu.db
ENTRYPOINT ["python", "-m", "src.cli"]
CMD ["--help"]
