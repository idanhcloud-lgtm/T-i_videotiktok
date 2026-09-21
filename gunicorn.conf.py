"""Gunicorn settings, read automatically when the app starts on Render.

Downloading a video happens inside the request, so the worker needs far more
than gunicorn's 30 second default: a slow platform response used to abort the
worker mid-download and return a bare 500 instead of a readable message.
"""

# Render's free instance has one CPU and 512 MB, so keep a single worker and
# serve concurrent downloads with threads instead of extra processes.
workers = 1
threads = 4

timeout = 300
graceful_timeout = 60

# Requests are long-lived; let the platform's proxy hold connections open.
keepalive = 65
