FROM alpine:3.20 AS builder

RUN apk add --no-cache \
    build-base \
    cmake \
    gcc \
    g++ \
    make \
    linux-headers

WORKDIR /build

COPY CMakeLists.txt .
COPY include/ include/
COPY src/ src/
COPY tests/ tests/

RUN mkdir build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release .. && \
    cmake --build . --config Release -j$(nproc) && \
    ./test_cpp_kernel_invariants

FROM alpine:3.20 AS runtime

RUN apk add --no-cache libstdc++ libgcc

WORKDIR /app
COPY --from=builder /build/build/edge_daemon /app/edge_daemon
COPY --from=builder /build/build/test_cpp_kernel_invariants /app/test_cpp_kernel_invariants

ENV SHM_ARENA_NAME=/ndtm_tensor_arena
ENV SHM_ARENA_SIZE_MB=64

EXPOSE 50051

ENTRYPOINT ["/app/edge_daemon"]
