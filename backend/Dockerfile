FROM python:3.11-slim

# 中文字体（图表用），不装的话导出的图表和 PPT 里中文会变方框
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 2026-09-30 前后端分离结构：仓库根 = backend/ + frontend/ + docs/
# 运行目录固定在 /app/backend（wsgi.py 会 chdir 到自身所在目录，
# competition.db / uploads / generated / tmp_export 都落在 backend/ 内）
WORKDIR /app/backend

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 构建上下文必须是仓库根（docker build ..），不是 backend/
COPY backend/ .
COPY frontend/ /app/frontend/
COPY docs/ /app/docs/

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

# workers 必须为 1：异步任务状态存在内存里，多进程会让轮询拿不到进度
CMD gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 600
