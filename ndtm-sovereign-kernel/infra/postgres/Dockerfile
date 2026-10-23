FROM pgvector/pgvector:pg16

# Install PostGIS 3 for spatial point process calculations and geodesic distances
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-16-postgis-3 \
    postgresql-16-postgis-3-scripts \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

LABEL maintainer="NDTM Sovereign Kernel Architecture Team"
LABEL description="PostgreSQL 16 with pgvector 0.7 and PostGIS 3.4 for multimodal spatiotemporal vector mesh"
