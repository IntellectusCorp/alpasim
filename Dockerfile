# Example command (run from repo root):
#   docker build --secret id=netrc,src=$HOME/.netrc -t alpasim_base:latest -f Dockerfile .

FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    cmake \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Build and install CycloneDDS C library (required by cyclonedds Python package)
RUN git clone --branch 0.10.5 --depth 1 https://github.com/eclipse-cyclonedds/cyclonedds.git /tmp/cyclonedds && \
    mkdir /tmp/cyclonedds/build && \
    cd /tmp/cyclonedds/build && \
    cmake .. -DCMAKE_INSTALL_PREFIX=/opt/cyclonedds -DBUILD_EXAMPLES=OFF -DBUILD_TESTING=OFF && \
    cmake --build . --parallel $(nproc) && \
    cmake --install . && \
    rm -rf /tmp/cyclonedds

ENV CYCLONEDDS_HOME=/opt/cyclonedds

COPY . /repo

# Configure uv
ENV UV_LINK_MODE=copy

# Compile protos
WORKDIR /repo/src/grpc
RUN --mount=type=secret,id=netrc,target=/root/.netrc \
    --mount=type=cache,target=/root/.cache/uv \
    NETRC=/root/.netrc uv sync --package alpasim_grpc
RUN uv run compile-protos --no-sync

WORKDIR /repo

RUN --mount=type=secret,id=netrc,target=/root/.netrc \
    --mount=type=cache,target=/root/.cache/uv \
    NETRC=/root/.netrc uv sync --all-packages

ENV UV_CACHE_DIR=/tmp/uv-cache
ENV UV_NO_SYNC=1
