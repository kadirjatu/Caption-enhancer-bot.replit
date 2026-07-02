FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first (layer cache)
COPY requirements.txt .

# Install Python packages (deduplicated)
RUN pip install --no-cache-dir \
    python-dotenv \
    pyTelegramBotAPI \
    requests \
    google-auth \
    google-api-python-client \
    google-genai \
    faster-whisper \
    flask \
    aiofiles \
    opencv-python-headless \
    Pillow \
    basicsr \
    facexlib \
    gfpgan \
    realesrgan

# Copy all project files
COPY . .

# Create required directories
RUN mkdir -p results tmp

# Expose Flask port
EXPOSE 5000

# Start bot (which also starts Flask webapp internally)
CMD ["python", "bot.py"]
