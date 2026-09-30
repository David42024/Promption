FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml LIBRARY.md ./
COPY promption/ ./promption/
COPY src/ ./src/
WORKDIR /app/chat-service
COPY chat-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY chat-service/app/ ./app/
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
