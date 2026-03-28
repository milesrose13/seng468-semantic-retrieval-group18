SENG 468 Project Post-Checkpoint Sprint Plan

March 28-April 20, 2026

## Done at checkpoint

- Auth endpoints (signup, login with JWT)
- Document endpoints (upload, list, delete)
- Search endpoint (semantic search, top 5 results, user-filtered)
- RabbitMQ worker for async PDF processing
- MinIO, PostgreSQL, Qdrant all running in Docker Compose
- CI with GitHub Actions (ruff + pytest)
- Initial load testing at 10 and 50 concurrent users (scripts not in repo)

## Remaining work

### Miles

March 28 - April 3
- Add Redis to docker-compose, cache search query results
- Move PDF upload into the worker so it doesn't block the API
- Improve document chunking for large PDFs (100+ pages)
- CORS middleware and error handling

April 4 - 10
- Fix bottlenecks found during load testing
- Architecture diagram for report
- Write implementation details and architecture sections of report

April 11 - 17
- Simple frontend for video demo
- Finish report sections
- Record video together

### Noah

March 28 - April 3
- Nginx load balancer with multiple API instances
- Fix auth performance (bcrypt cost or async hashing)
- Write Locust test scripts

April 4 - 10
- Run load tests (10, 50, 100 users), capture metrics and graphs
- Re-run after optimizations for before/after comparison
- Write design decisions and performance sections of report

April 11 - 17
- DB indexing and query optimization if applicable
- Finish report sections
- Record video together

### Both

- April 5: Report outline started
- April 13: Collaboration and AI disclosure sections
- April 15: Report finalized (PDF)
- April 16-17: Record presentation video
- April 18: README and .env.example cleanup
- April 19: Test docker-compose on a clean machine
- April 20: Submit on Brightspace

## Bonus if we feel like it

- Prometheus + Grafana monitoring (Noah)
- Hybrid search or reranking (Miles)
- Any other optimization that gets us a measurable improvement

## Known issues from checkpoint

- Auth latency jumps 10x at 50 users (bcrypt)
- POST /documents had 111 failures at 50 users (blocking upload)
- No caching layer
- Single API instance, no horizontal scaling
