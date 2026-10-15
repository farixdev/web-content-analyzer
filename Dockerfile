FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=7860

WORKDIR /app

# Create non-root user for cloud security & Hugging Face Spaces compatibility
RUN useradd -m -u 1000 user

# Install Python web dependencies
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# Copy application source
COPY --chown=user:user . /app

USER user

EXPOSE 7860

CMD ["python", "web_server.py"]
