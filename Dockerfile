FROM python:3.11-slim

# 接收由 buildx 注入的架构变量（常见值：amd64、arm64）
ARG TARGETARCH

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 按架构拷贝 CloudflareSpeedTest
COPY cfst_linux_${TARGETARCH}/cfst /usr/local/bin/
RUN chmod +x /usr/local/bin/cfst

# 复制应用代码
COPY . .

# 根据架构删除不需要的cfst目录
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        rm -rf /app/cfst_linux_arm64; \
    elif [ "$TARGETARCH" = "arm64" ]; then \
        rm -rf /app/cfst_linux_amd64; \
    fi

# 创建配置目录
RUN mkdir -p /app/config /app/logs

# 暴露端口
ARG APP_PORT=23333
ENV APP_PORT=${APP_PORT}
EXPOSE ${APP_PORT}

# 启动应用
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT}"]