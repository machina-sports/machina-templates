# Machina Deployment Guide

## Quick Start

### 1. Environment Setup

Create or update your `.env` file:

```bash
# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_PUBSUB_URL=redis://localhost:6379/1

# MongoDB
MONGODB_URL=mongodb://localhost:27017/machina

# Gunicorn
GUNICORN_WORKERS=4

# Streaming Configuration
MAX_CONCURRENT_STREAMS=10
STREAM_TIMEOUT_SECONDS=300
CIRCUIT_BREAKER_THRESHOLD=5

# Logging
LOG_LEVEL=info

# Feature Flags
SCHEDULERS=1  # Enable background schedulers

# API Version
MACHINA_CLIENT_VERSION=2.0.0
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Key dependencies:
- `gevent>=23.9.0` - Async I/O for web workers
- `gunicorn>=21.2.0` - Production WSGI server
- `redis>=4.0.0` - Redis client for Pub/Sub
- `celery` - Distributed task queue

### 3. Start Services

#### Option A: Docker Compose (Recommended)

```bash
# Start all services (API + Celery workers)
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

#### Option B: Manual (Production)

```bash
# Terminal 1: Start API with gunicorn
./start-prod.sh

# Terminal 2: Start Celery streaming workers
celery -A core worker -l INFO -c 6 -Q streaming_priority --include=core.agent.executor_stream

# Terminal 3: Start normal Celery workers
celery -A core worker -l INFO -c 4 -Q high_priority,normal_priority,low_priority
```

## Architecture Overview

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /agent/stream/{id}
       ▼
┌──────────────┐     Submit Task      ┌─────────────┐
│  Gunicorn    │ ─────────────────────>│   Celery    │
│  (gevent)    │                       │   Workers   │
│  Port 5003   │<─────────────────────│ (6 workers) │
└──────┬───────┘   Stream via Redis   └─────────────┘
       │ Pub/Sub
       ▼
  Client receives
  streaming chunks
```

**Key Points**:
- Single gunicorn instance on port 5003
- Gevent workers handle both regular and streaming
- Celery workers do all heavy execution
- Web workers only manage HTTP connections

## Verification

### 1. Check Services

```bash
# Check API is running
curl http://localhost:5003/system/client-health-check

# Expected: {"data": "System client is healthy"}
```

### 2. Check Streaming Health

```bash
curl http://localhost:5003/system/streaming-health | jq
```

Expected response:
```json
{
  "status": "healthy",
  "circuit_breakers": {
    "agent_streaming": {
      "state": "closed",
      "failure_count": 0,
      "threshold": 5
    }
  },
  "redis_streams": {
    "active_streams": 0,
    "redis_healthy": true
  },
  "web_worker_streams": {
    "active": 0,
    "max": 10,
    "available": 10
  }
}
```

### 3. Test Streaming Endpoint

```bash
curl -X POST http://localhost:5003/agent/stream/{agent_id} \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {your_token}" \
  -d '{
    "messages": [
      {"role": "user", "content": "Hello"}
    ],
    "stream_workflows": true
  }'
```

Expected: NDJSON stream with `start`, `content`, `done` events

## Scaling

### Vertical (Single Server)

Increase resources on one machine:

```bash
# More web workers
export GUNICORN_WORKERS=8

# More Celery workers
celery -A core worker -c 12 -Q streaming_priority  # 6 → 12

# More concurrent streams
export MAX_CONCURRENT_STREAMS=20
```

### Horizontal (Multiple Servers)

Deploy multiple API instances behind load balancer:

```
┌────────────────┐
│ Load Balancer  │
└────────┬───────┘
         │
    ┌────┴────┬──────────┐
    │         │          │
┌───▼──┐  ┌──▼──┐   ┌───▼──┐
│ API1 │  │ API2│   │ API3 │
│10/10 │  │10/10│   │10/10 │
└──┬───┘  └──┬──┘   └───┬──┘
   │         │          │
   └─────────┴──────────┘
             │
      ┌──────▼──────┐
      │    Redis    │
      │   (shared)  │
      └─────────────┘
```

Total capacity: 3 instances × 10 streams = **30 concurrent streams**

## Troubleshooting

### Issue: "Too Many Concurrent Streams" (429)

**Solution**: Increase `MAX_CONCURRENT_STREAMS` or add more API instances

```bash
export MAX_CONCURRENT_STREAMS=20
./start-prod.sh
```

### Issue: "Service Temporarily Unavailable" (503)

**Cause**: Circuit breaker opened

**Solution**:
1. Check logs for failures
2. Fix underlying issue
3. Reset circuit breaker:

```bash
curl -X POST http://localhost:5003/system/circuit-breaker/reset/agent_streaming \
  -H "Authorization: Bearer {admin_token}"
```

### Issue: Streams Timeout After 5 Minutes

**Solution**: Increase timeout

```bash
export STREAM_TIMEOUT_SECONDS=600  # 10 minutes
./start-prod.sh
```

### Issue: Redis Connection Errors

**Solution**: Check Redis is running and accessible

```bash
# Test Redis
redis-cli -u $REDIS_PUBSUB_URL ping

# Should return: PONG
```

## Production Checklist

- [ ] Environment variables configured
- [ ] Redis running and accessible
- [ ] MongoDB running and accessible
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Gunicorn configuration reviewed (`gunicorn_config.py`)
- [ ] Celery workers started (all queues)
- [ ] Health checks passing
- [ ] Streaming health endpoint healthy
- [ ] Test streaming endpoint works
- [ ] Monitoring configured
- [ ] Logs being collected
- [ ] Circuit breaker threshold appropriate
- [ ] Connection limits appropriate
- [ ] Load balancer configured (if multiple instances)

## Recommended Production Settings

For a server with 8 CPU cores and 16GB RAM:

```bash
# Web layer
GUNICORN_WORKERS=4  # 4 gevent workers × 1000 connections = 4000 concurrent

# Execution layer (Celery)
Streaming: 6 workers (CPU-bound tasks)
High Priority: 4 workers
Normal Priority: 2 workers
Low Priority: 1 worker

# Connection management
MAX_CONCURRENT_STREAMS=15
STREAM_TIMEOUT_SECONDS=300
CIRCUIT_BREAKER_THRESHOLD=5
```

