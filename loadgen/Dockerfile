FROM python:3.12-slim
WORKDIR /srv
RUN pip install --no-cache-dir requests==2.32.3 boto3==1.35.24 PyJWT==2.9.0
COPY loadgen.py .
COPY security.py .
CMD ["python", "-u", "loadgen.py"]
