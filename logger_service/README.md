# Logger Service

This microservice consumes token usage events from Redis and forwards them to Logstash (elk.54ucl.com:5044).

Files:
- `logstash_handler.py`: Sends JSON over TCP to Logstash.
- `redis_client.py`: Simple Redis enqueue/dequeue helpers.
- `consumer.py`: Consumer and producer classes for queue handling.
- `high_performance.py`: Optional high-performance producer/consumer implementations for high throughput.
- `start_logger_service.py`: Entrypoint to run the logger service as a standalone process.

Quick start (local):

1. Ensure Redis is running and accessible.
2. Ensure Logstash is reachable at `elk.54ucl.com:5044`.
3. From `semantic_kernel` directory run:

```bash
python start_logger_service.py
```

Container:

Build and run the Docker image (from `semantic_kernel`):

```bash
docker build -t semantic-logger -f logger_service/Dockerfile .
docker run -e REDIS_HOST=redis -e LOGSTASH_HOST=elk.54ucl.com semantic-logger
```

Design notes:
- Keep SK API lightweight: SK should only create `TokenUsage` events and enqueue them to Redis.
- Logger Service handles batching, retries, and forwarding to Logstash.
- The `high_performance.py` module is optional and provides buffering and consumer pooling for high throughput.
