FROM python:3.12-alpine
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install -r requirements.txt
COPY ikea_light_fixer.py /app/ikea_light_fixer.py
ENTRYPOINT ["python", "/app/ikea_light_fixer.py"]
