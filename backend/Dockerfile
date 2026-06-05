# ==============================================================================
# StockkAsk FastAPI Backend — Secure Multi-Stage Dockerfile
# ==============================================================================
# WHAT IS A DOCKERFILE?
# A Dockerfile is a recipe or script containing instructions to build a container image. 
# Think of an "image" as a snapshot of a computer (with OS, files, and libraries) 
# that runs our code. A "container" is a living, running instance of that snapshot.
#
# WHAT IS A MULTI-STAGE BUILD?
# In traditional Docker files, you download compilers (like gcc, pip, git) and code 
# files all in one image. This makes the image massive and insecure (because hacker tools 
# are left inside). 
# A "multi-stage" build uses multiple "FROM" statements:
#   1. Stage 1 (Builder): We install all compilers and build dependencies.
#   2. Stage 2 (Runner): We start with a clean OS, copy ONLY the compiled packages 
#      and code from Stage 1, and discard the heavy build tools.
# This results in an image that is 3-4x smaller and significantly more secure!
# ==============================================================================

# ==============================================================================
# STAGE 1: BUILDER
# ==============================================================================
# 'FROM' starts a new build stage. We use python:3.12-slim (a lightweight Linux image).
# 'AS builder' names this stage so we can copy files from it in the next stage.
FROM python:3.12-slim AS builder

# 'WORKDIR' sets the working directory inside the container. If it doesn't exist,
# Docker creates it. All subsequent commands (RUN, COPY) run inside this folder.
WORKDIR /build

# Disable writing .pyc files to save space during build
ENV PYTHONDONTWRITEBYTECODE=1
# Prevent Python from buffering stdout/stderr (so we get logs immediately in Jenkins/Docker)
ENV PYTHONUNBUFFERED=1

# Install OS-level build dependencies (some Python packages require C compilers or 
# git during installation). We clean up apt cache afterwards to save space.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 'COPY' transfers files from your computer (host) into the container's filesystem.
# Here, we copy requirements.txt into the /build folder.
COPY requirements.txt .

# Create a virtual environment inside /opt/venv. This keeps our dependencies 
# isolated and makes it easy to copy all packages as a single folder to Stage 2.
# We then upgrade pip and install our Python packages into this virtual environment.
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# ==============================================================================
# STAGE 2: RUNNER (FINAL RUNTIME IMAGE)
# ==============================================================================
# We start fresh with a clean, slim Python image.
# Build tools from Stage 1 are completely excluded from this image!
FROM python:3.12-slim AS runner

WORKDIR /app

# Configure environmental settings
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Add our virtual environment's bin folder to the system PATH.
# This allows the container to run packages like 'uvicorn' or 'pytest' directly.
ENV PATH="/opt/venv/bin:$PATH"

# --- SECURITY BOUNDARY: Create a Non-Root User ---
# By default, Docker runs containers as 'root' (admin). If a hacker exploits your 
# FastAPI code, they would gain full root control of the host system. 
# We create a restricted system user named 'stockkbot' to run the app safely.
RUN groupadd -g 1000 stockkbot && \
    useradd -u 1000 -g stockkbot -m -s /bin/bash stockkbot

# Copy the compiled virtual environment containing all dependencies from the 'builder' stage.
# '--from=builder' points directly to Stage 1.
COPY --from=builder /opt/venv /opt/venv

# Copy our application files into the /app directory.
# '--chown=stockkbot:stockkbot' ensures our restricted user owns these files, not root.
COPY --chown=stockkbot:stockkbot . .

# --- SECURITY BOUNDARY: Drop Privileges ---
# Tell Docker to run all subsequent commands and the main process as our restricted user.
USER stockkbot

# 'EXPOSE' tells Docker that the container will listen on port 8000 at runtime.
# This serves as documentation and allows port-mapping.
EXPOSE 8000

# --- SECURE CONTAINER HEALTHCHECK ---
# Docker monitors container health automatically. Instead of installing curl (which 
# has security bugs and bloating), we use a built-in Python script to hit our FastAPI 
# health endpoint. If it returns 200, the container is healthy. If not, Docker restarts it.
#   --interval: how often to check (every 30 seconds)
#   --timeout: maximum time allowed for the check (5 seconds)
#   --start-period: wait 10 seconds on boot to let FastAPI start up
#   --retries: fail 3 times in a row before marking container as unhealthy
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# 'CMD' specifies the command that runs when the container starts.
# We run uvicorn with:
#   - 4 workers (enables running 4 requests in parallel on multi-core systems)
#   - --no-access-log (quiets normal request logging, structlog inside main.py handles it)
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--log-level", "info", \
     "--no-access-log"]
