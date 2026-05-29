FROM python:3.10

WORKDIR /app

# 先升级 pip（但不要太新）
RUN pip install --upgrade pip==24.0 setuptools wheel

COPY requirements.txt .

# 防止 pip resolver bug（非常关键）
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_CACHE_DIR=1

RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]