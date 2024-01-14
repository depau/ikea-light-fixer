FROM python:3.12-alpine
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install -r requirements.txt
COPY . /app
ENTRYPOINT ["python", "/app/brightness_fixer.py"]
