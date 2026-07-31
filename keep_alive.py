"""
Render's free "Web Service" plan expects the app to open an HTTP port and
respond to health checks — otherwise it times out and kills the deploy,
even though our Telegram bot itself only does polling and needs no port.

This starts a tiny Flask server in a background thread just so Render sees
something listening on $PORT. It doesn't do anything else.
"""
import os
import logging
import threading
from flask import Flask

logging.getLogger("werkzeug").setLevel(logging.ERROR)  # silence Flask's request logs

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is alive."


def _run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
