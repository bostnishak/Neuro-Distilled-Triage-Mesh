FROM alpine:3.19

RUN apk add --no-cache \
    pgbouncer \
    postgresql-client \
    su-exec \
    ca-certificates \
    tzdata

RUN mkdir -p /etc/pgbouncer /var/log/pgbouncer /var/run/pgbouncer && \
    chown -R postgres:postgres /etc/pgbouncer /var/log/pgbouncer /var/run/pgbouncer && \
    chmod 755 /var/log/pgbouncer /var/run/pgbouncer && \
    chmod 700 /etc/pgbouncer

COPY pgbouncer.ini /etc/pgbouncer/pgbouncer.ini
COPY userlist.txt /etc/pgbouncer/userlist.txt

RUN chown postgres:postgres /etc/pgbouncer/pgbouncer.ini /etc/pgbouncer/userlist.txt && \
    chmod 600 /etc/pgbouncer/pgbouncer.ini /etc/pgbouncer/userlist.txt

EXPOSE 6432

HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \
  CMD pg_isready -h 127.0.0.1 -p 6432 -U ndtm_admin -d ndtm_sovereign || exit 1

USER postgres

CMD ["pgbouncer", "/etc/pgbouncer/pgbouncer.ini"]
