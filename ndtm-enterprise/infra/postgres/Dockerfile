# ==============================================================================
# NDTM Enterprise PostgreSQL 16 with PostGIS & pgvector Extension
# ==============================================================================
FROM postgis/postgis:16-3.4

LABEL maintainer="NDTM Systems Architecture Team <architect@ndtm.enterprise>"
LABEL description="PostgreSQL 16 engine fortified with PostGIS spatial and pgvector HNSW indexing"

# Install compilation tools and postgresql-16-pgvector
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-16-pgvector \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy initialization SQL scripts
COPY init_schema.sql /docker-entrypoint-initdb.d/01_init_schema.sql

# Set optimal database tuning parameters for vector search & postgis
RUN echo "shared_preload_libraries = 'pg_stat_statements'" >> /usr/share/postgresql/postgresql.conf.sample && \
    echo "work_mem = 64MB" >> /usr/share/postgresql/postgresql.conf.sample && \
    echo "maintenance_work_mem = 256MB" >> /usr/share/postgresql/postgresql.conf.sample && \
    echo "max_parallel_workers_per_gather = 4" >> /usr/share/postgresql/postgresql.conf.sample

HEALTHCHECK --interval=5s --timeout=5s --retries=10 \
    CMD pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" || exit 1
