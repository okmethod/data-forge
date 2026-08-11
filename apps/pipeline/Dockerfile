# syntax=docker/dockerfile:1
# check=error=true

# --build-arg によりバージョンを指定する（デフォルトなし。必須指定）
ARG PYTHON_VERSION=x
ARG UV_VERSION=x

# ==============================================================================
# uv バイナリ取得用
# ==============================================================================
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ==============================================================================
# ベースイメージ
# ==============================================================================
FROM python:${PYTHON_VERSION}-slim AS base
COPY --from=uv /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_PREFERENCE=only-system \
    PATH="/opt/venv/bin:$PATH"

# config.py の REPO_ROOT=parents[4] を満たすため、リポジトリと同じ階層に置く
WORKDIR /repo/apps/pipeline

# 依存だけ先に入れてレイヤーキャッシュを効かせる（プロジェクト本体は後で）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --extra dev

# プロジェクト本体を editable で導入（bind mount 上の src 変更が即反映される）
# hatchling が readme=README.md を参照するため同梱
COPY src ./src
COPY README.md ./
RUN uv sync --frozen --extra dev

CMD ["data-forge", "--help"]
