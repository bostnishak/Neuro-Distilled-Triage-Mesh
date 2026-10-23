# ==============================================================================
# Multi-Stage Dockerfile for NDTM C++20 Sovereign Edge Data Plane Node
# ==============================================================================

# Stage 1: Build Environment
FROM gcc:12-bookworm AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake \
    ninja-build \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY CMakeLists.txt .
COPY include/ include/
COPY src/ src/

RUN cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --parallel $(nproc)

# Stage 2: Hardened Unprivileged Runtime
FROM debian:bookworm-slim AS runtime

RUN useradd -u 10002 -m -s /bin/bash edgeuser \
    && mkdir -p /app/models \
    && chown -R edgeuser:edgeuser /app

WORKDIR /app

COPY --from=builder /build/build/edge_cpp_node /usr/local/bin/edge_cpp_node

USER edgeuser:edgeuser

ENV NODE_ID="EDGE_NODE_ISTANBUL_01"
ENV GATEWAY_ENDPOINT="backend:50051"

ENTRYPOINT ["edge_cpp_node"]
CMD ["EDGE_NODE_ISTANBUL_01", "backend:50051"]
