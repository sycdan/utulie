# uuid.uuid7() is 3.14-only stdlib -- state/repo.py depends on it directly.
FROM python@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2 AS base

# git: the state repo IS a git repo, read and written with real git commands,
# not a library. openssh-client: pushing to GitHub over a mounted deploy key.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The printer (printer/) is not here on purpose: it owns a physical COM port
# and runs natively on the machine the printer is plugged into, never in a
# container. See printer/README.md.
COPY state/ state/
COPY api/ api/

RUN git config --system user.email "utulie@localhost" \
    && git config --system user.name "utulie" \
    && git config --system --add safe.directory '*'

# GitHub's published ed25519 host key, pinned rather than trust-on-first-use.
# /tmp does not persist across restarts, so TOFU would mean re-accepting a
# fresh host key on every container start -- pinning it here means a real
# MITM on that connection fails loud instead of being silently accepted.
RUN mkdir -p /etc/ssh && \
    echo 'github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl' \
    > /etc/ssh/ssh_known_hosts

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c \
    "import urllib.request as u; u.urlopen('http://localhost:8080/health', timeout=2)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
