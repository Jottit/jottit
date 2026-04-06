web: gunicorn app:app --bind 0.0.0.0:8080 --workers 2 --timeout 30
worker: python -m workers.job_worker
