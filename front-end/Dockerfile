FROM python:3.11
RUN mkdir .streamlit
COPY .streamlit/config.toml .streamlit/config.toml

COPY . .
RUN pip install -r requirements.txt
RUN pip install visionai-0.0.6-py3-none-any.whl --force-reinstall
RUN make ./app

EXPOSE 8080

CMD ["streamlit", "run", "app/Home.py", "--server.port=8080", "server.address=0.0.0.0"]
