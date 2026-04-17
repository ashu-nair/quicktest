# Use mirror registry for faster pulls in regions with limited Docker Hub access
FROM docker.mirrors.ustc.edu.cn/library/python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn numpy scikit-learn joblib

COPY app /app
COPY model /model

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
