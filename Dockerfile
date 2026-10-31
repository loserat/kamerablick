FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app/ /app/
COPY pi/agent.py pi/kiosk.py pi/session.py pi/cec_bridge.py pi/player_health.py /opt/kamerablick/pi/
RUN useradd --uid 10001 --create-home app && mkdir /data && chown app:app /data
USER app
ENV DATA_DIR=/data BIND=127.0.0.1 PORT=8088
EXPOSE 8088
CMD ["python", "server.py"]
