FROM python:3.11

COPY . .
RUN pip install -r requirements.txt
RUN make .

EXPOSE 8080

CMD exec gunicorn --bind :$PORT --workers 1 --threads 1 --timeout 0 main:app
