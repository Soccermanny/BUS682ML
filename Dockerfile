FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy data and enrichment script
COPY project_2_data_filled_with_api.csv .
COPY enrich_with_validation.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Volume for output
VOLUME ["/app/output"]

# Run the enrichment script
CMD ["python", "enrich_with_validation.py"]
