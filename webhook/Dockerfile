FROM python:3.12-slim
WORKDIR /srv
COPY webhook.py .
EXPOSE 5001
CMD ["python", "-u", "webhook.py"]
