FROM python:3.12.8-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN addgroup --system --gid 10001 osl && adduser --system --uid 10001 --ingroup osl osl
COPY apps/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt
COPY apps/api/app ./app
COPY detections ./detections
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

