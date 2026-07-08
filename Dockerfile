FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY proxmox_install_automation/ ./proxmox_install_automation/
COPY skillhub/ ./skillhub/
COPY config.example.yaml ./config.example.yaml
COPY setup.py ./setup.py
COPY README.md ./README.md

# Install the package
RUN pip install --no-cache-dir -e .

# Create data directory
RUN mkdir -p /app/data

# Expose the application port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run the application
CMD ["python", "-m", "proxmox_install_automation.cli", "serve", "--host", "0.0.0.0", "--port", "5000"]
