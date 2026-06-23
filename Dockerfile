# Moka MCP Server —— 自托管 HTTP 端点镜像
FROM python:3.11-slim

# 不写 .pyc、日志实时刷新
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先拷贝项目元数据与源码，安装依赖
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# HTTP 传输默认值（敏感值通过 env_file / -e 注入，不写进镜像）
ENV MOKA_TRANSPORT=http \
    MOKA_HTTP_HOST=0.0.0.0 \
    MOKA_HTTP_PORT=8000 \
    MOKA_HTTP_PATH=/mcp

EXPOSE 8000

CMD ["moka-mcp-server"]
