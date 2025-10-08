FROM python:3.10-slim

WORKDIR /app

# Copy only necessary files for logger service
COPY ../requirements.txt /app/requirements.txt
COPY ../start_logger_service.py /app/start_logger_service.py
COPY ./ /app/logger_service/

# Install runtime deps
RUN pip install --no-cache-dir -r /app/requirements.txt

ENV PYTHONUNBUFFERED=1

# Run the logger service
CMD ["python", "/app/start_logger_service.py"]
