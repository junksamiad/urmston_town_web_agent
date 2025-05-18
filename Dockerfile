# 1. Use an official Python 3.11 slim image as a parent image
FROM python:3.11-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# 2. Install dependencies
COPY requirements.txt .
# Install git first as it's needed for editable git dependencies in requirements.txt
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*
# Upgrade pip and install requirements
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy application code
# Copy the rest of the application code into the working directory
COPY . .

# Expose the port the app runs on (default for Uvicorn with FastAPI is 8000)
EXPOSE 8000

# The command to run when the container starts
CMD ["uvicorn", "main_web:app", "--host", "0.0.0.0", "--port", "8000"] 