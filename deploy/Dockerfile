FROM python:3.13-slim
WORKDIR /app
COPY src ./src
ENV BND_TRADING_MODE=PAPER BND_ALLOW_LIVE_AI=false PYTHONUNBUFFERED=1
# Doar PAPER: safety.py refuză orice altceva.
CMD ["python", "-m", "src.bnd.paper_runner", "--state", "/data/paper.sqlite", "--data-dir", "/data/candles", "--audit-log", "/data/audit.jsonl", "--report", "/data/REPORT.md", "--json", "/data/last_run.json"]
