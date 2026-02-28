# Use an official lightweight Python image
FROM python:3.11-slim

# Install the Docker CLI and SSH client. 
# The Docker CLI is required because our FastAPI router leverages 'subprocess.run(["docker", ...])'
RUN apt-get update && \
    apt-get install -y docker.io openssh-client && \
    rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Copy the requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the API port
EXPOSE 8000

# Run the FastAPI server
CMD ["python", "main.py"]
