FROM python:3.11-slim

# OS tools (개미군단 운용에 유용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    jq \
    shellcheck \
  && rm -rf /var/lib/apt/lists/*

# Python 품질 도구
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir \
    ruff \
    mypy \
    pytest \
    black \
    coverage

# bind mount 파일 소유권 꼬임 방지용 유저
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} ant && useradd -m -u ${UID} -g ${GID} ant
USER ant

WORKDIR /work
