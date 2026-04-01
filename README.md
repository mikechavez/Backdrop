# Backdrop

A real-time cryptocurrency news aggregator that collects articles from various sources, performs sentiment analysis, and provides insights into market trends.

## Features

- **News Collection**: Fetches cryptocurrency news from multiple sources using NewsAPI
- **Sentiment Analysis**: Analyzes article sentiment using TextBlob's NLP capabilities
- **Trend Analysis**: Tracks sentiment trends over time
- **RESTful API**: FastAPI-based endpoints for accessing news and analysis
- **Background Processing**: Celery workers for async task processing
- **Containerized**: Docker Compose setup for easy deployment

## Tech Stack

- **Backend**: Python 3.9+, FastAPI
- **Database**: PostgreSQL
- **Cache & Message Broker**: Redis
- **Task Queue**: Celery
- **NLP**: TextBlob
- **Containerization**: Docker, Docker Compose

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.9+
- Poetry (for local development)
- NewsAPI key

### Environment Setup

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Update the `.env` file with your configuration:
   ```
   NEWS_API_KEY=your_newsapi_key
   DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/crypto_news
   CELERY_BROKER_URL=redis://localhost:6379/0
   CELERY_RESULT_BACKEND=redis://localhost:6379/0
   ```

### Running with Docker Compose

```bash
docker-compose up -d
```

This will start:
- FastAPI app on http://localhost:8000
- PostgreSQL database
- Redis server
- Celery worker
- Celery beat (for scheduled tasks)

### Local Development

1. Install dependencies:
   ```bash
   poetry install
   ```

2. Run database migrations:
   ```bash
   alembic upgrade head
   ```

3. Start the development server:
   ```bash
   uvicorn crypto_news_aggregator.main:app --reload
   ```

4. Start Celery worker:
   ```bash
   celery -A crypto_news_aggregator.tasks worker --loglevel=info
   ```

## API Documentation

Once the application is running, you can access:

- **API Docs**: http://localhost:8000/docs
- **Redoc**: http://localhost:8000/redoc

## Testing

Run unit tests:
```bash
pytest tests/
```

Run integration tests:
```bash
pytest tests/integration/
```

## Project Structure

```
├── src/
│   └── crypto_news_aggregator/
│       ├── api/              # API endpoints
│       ├── core/             # Core functionality
│       ├── db/               # Database models and migrations
│       ├── tasks/            # Celery tasks
│       └── main.py           # FastAPI application
├── tests/                    # Test files
├── scripts/                  # Utility scripts
├── docker-compose.yml        # Docker Compose configuration
└── pyproject.toml           # Project metadata and dependencies
```

## Test Types in This Project

### Unit Tests
- Test individual components in isolation
- Mock external dependencies
- Fast execution
- Example: `test_sentiment_analyzer.py`

### Integration Tests
- Test interactions between components
- Use real database and services
- Slower but more realistic
- Example: `test_sentiment_pipeline.py`

## License

This project and all its contents are Copyright © 2025 Michael Lee Chavez. All rights reserved.

**All rights reserved.** No part of this project may be reproduced, distributed, or transmitted in any form or by any means, including photocopying, recording, or other electronic or mechanical methods, without the prior written permission of the copyright owner.

For permission requests, please contact the author.
