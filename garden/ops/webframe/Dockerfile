# The web frame as an always-on test server (see deploy.sh). The garden code and
# art are mounted at /app, so a redeploy only needs a container restart.
FROM python:3.13-slim
RUN pip install --no-cache-dir "Pillow>=10.1" "numpy>=1.24"
WORKDIR /app
ENV PYTHONUNBUFFERED=1
CMD ["sh", "-c", "exec python webframe.py --host 0.0.0.0 --panel-hours --station \"$STATION\" ${WALL:+--wall \"$WALL\"}"]
