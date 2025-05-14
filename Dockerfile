FROM python:3.11-slim
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# don’t COPY your app here—let it be bind-mounted at runtime
CMD python manage.py migrate --noinput \
    && python manage.py runserver 0.0.0.0:8000