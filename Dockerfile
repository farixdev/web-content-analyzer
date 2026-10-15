FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

WORKDIR /app

# Create non-root user for cloud security
RUN useradd -m -u 1000 user

# Install Python web dependencies
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# Copy application source
COPY --chown=user:user . /app

USER user

EXPOSE 10000

CMD ["python", "web_server.py"]
