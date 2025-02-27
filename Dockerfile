# Use a lightweight Python base image
FROM python:3.12

# Update system packages (optional, but often useful)
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Create and switch to the /app directory
WORKDIR /app

# Copy requirements first (for caching) and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your code into the image
COPY . .

# EXPOSE the TCP server port you plan to use
EXPOSE 8899

# Finally, run the application
CMD ["python", "main.py"]
