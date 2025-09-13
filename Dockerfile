# Use miniconda3 as base image
FROM continuumio/miniconda3:latest

# Set working directory
WORKDIR /app

# Copy environment file first for better Docker layer caching
COPY environment.yml .

# Create the conda environment
RUN conda env create -f environment.yml

# Make RUN commands use the new environment
SHELL ["conda", "run", "-n", "vending-machine", "/bin/bash", "-c"]

# Copy the entire vm-py directory
COPY . .

# Create a non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose the port that FastAPI will run on
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD conda run -n vending-machine curl -f http://localhost:8000/status || exit 1

# Run the FastAPI application using conda environment
CMD ["conda", "run", "--no-capture-output", "-n", "vending-machine", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
