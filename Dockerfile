# Example command (run from repo root):
#   docker build --secret id=netrc,src=$HOME/.netrc -t alpasim_base:latest -f Dockerfile .

FROM nvcr.io/nvidia/pytorch:25.06-py3

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    cmake \
    libeigen3-dev \
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
    NETRC=/root/.netrc uv sync
RUN uv pip install --reinstall "setuptools<70" && uv run --no-sync compile-protos

WORKDIR /repo

# Sync all packages except physics (point-cloud-utils has no aarch64 wheel on PyPI)
RUN --mount=type=secret,id=netrc,target=/root/.netrc \
    --mount=type=cache,target=/root/.cache/uv \
    NETRC=/root/.netrc uv sync --all-packages --exclude-package alpasim-physics

# Reuse PyTorch from base image instead of uv-installed copy
RUN rm -rf /repo/.venv/lib/python3.12/site-packages/torch \
             /repo/.venv/lib/python3.12/site-packages/torchvision \
             /repo/.venv/lib/python3.12/site-packages/torchaudio && \
      ln -s /usr/local/lib/python3.12/dist-packages/torch /repo/.venv/lib/python3.12/site-packages/torch && \
      ln -s /usr/local/lib/python3.12/dist-packages/torchvision /repo/.venv/lib/python3.12/site-packages/torchvision && \
      ln -s /usr/local/lib/python3.12/dist-packages/torchaudio /repo/.venv/lib/python3.12/site-packages/torchaudio && \
      uv pip install "numpy<2"

# Install pre-built ARM64 wheel for point-cloud-utils, then sync physics
RUN if [ -f /repo/point_cloud_utils-0.35.0-cp312-cp312-linux_aarch64.whl ]; then \
    uv pip install /repo/point_cloud_utils-0.35.0-cp312-cp312-linux_aarch64.whl; \
    fi
RUN --mount=type=secret,id=netrc,target=/root/.netrc \
    --mount=type=cache,target=/root/.cache/uv \
    NETRC=/root/.netrc uv sync --package alpasim-physics

# Note: maglev.av has name collisions with PyAV (both use `import av`).
# Patch torchvision to trigger its "av not available" fallback path.
RUN for f in .venv/lib/python*/site-packages/torchvision/io/video.py \
             .venv/lib/python*/site-packages/torchvision/io/video_reader.py; do \
        [ -f "$f" ] && sed -i 's/import av$/raise ImportError("maglev.av collision")/' "$f"; \
    done || true

ENV UV_CACHE_DIR=/tmp/uv-cache
ENV UV_NO_SYNC=1
