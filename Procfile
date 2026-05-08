web: uvicorn main:app --host 0.0.0.0 --port $PORT
worker: celery -A crypto_news_aggregator.tasks worker --loglevel=info --queues=default,news,price,alerts,briefings
beat: celery -A crypto_news_aggregator.tasks beat --loglevel=info
bugops: python -m crypto_news_aggregator.bugops.monitor
