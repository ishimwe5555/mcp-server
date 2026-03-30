# Eddie MCP Server - Resto API Integration

Containerized MCP server with 15 geospatial data tools exposed via HTTP API for Intercom integration.

## Quick Start

### 1. Configure Environment
```bash
cp .env.example .env
# Edit .env with OAuth2 credentials:
# OAUTH2_CLIENT_ID, OAUTH2_USERNAME, OAUTH2_PASSWORD
```

### 2. Run Service
```bash
./quickstart.sh          # macOS/Linux
# or
quickstart.bat           # Windows
# or manually
docker-compose up -d
```

### 3. Access API
- Docs: `http://localhost:8000/docs`
- Health: `curl http://localhost:8000/health`
- Tools: `curl http://localhost:8000/tools`

## Intercom Integration

Call tools via HTTP POST:
```bash
curl -X POST http://localhost:8000/tools/search_data \
  -H "Content-Type: application/json" \
  -d '{"parameters": {"query": "satellite", "limit": 10}}'
```

For production, use your deployed URL (e.g., `https://your-domain.com/api/tools/...`)

## 15 Available Tools

**Authentication:** get_auth_token, check_auth_status
**Collections:** list_collections, get_collection_info, search_collection_features
**Search:** search_data, get_feature_details
**Users:** get_my_profile, get_user_profile, get_users, get_user_features
**Groups:** list_groups, get_group_info
**STAC:** get_stac_queryables, get_landing_page

See `/tools` endpoint for full details.

## Environment Setup

### Production/Server
Create `.env` on your server with:
```
OAUTH2_CLIENT_ID=your_production_id
OAUTH2_USERNAME=your_username
OAUTH2_PASSWORD=your_password
HOST=0.0.0.0
PORT=8000
DEBUG=false
REQUEST_TIMEOUT=30
```

Secure it:
```bash
chmod 600 .env
```

### Secret Management
- `.env` is **NEVER committed to git** (see `.gitignore`)
- `.env.example` is the template in git (no secrets)
- Store real credentials only on production server

## Deployment

### Docker Compose (Recommended)
```bash
docker-compose up -d          # Start
docker-compose logs -f        # View logs
docker-compose down           # Stop
```

### Kubernetes / Docker Swarm
Use environment variables or secrets manager. Container reads `OAUTH2_*` from environment.

## API Endpoints

- `GET /health` - Health check
- `GET /tools` - List available tools  
- `POST /tools/{tool_name}` - Execute tool with `{"parameters": {...}}`
- `GET /docs` - Interactive API documentation
- `GET /auth/status` - Check authentication

## Files

| File | Purpose |
|------|---------|
| `app.py` | MCP server with 15 tools |
| `service.py` | HTTP wrapper (FastAPI) |
| `Dockerfile` | Container definition |
| `docker-compose.yml` | Local/production deployment |
| `requirements.txt` | Python dependencies |
| `.env.example` | Configuration template (in git) |
| `.env` | Real credentials (not in git) |
| `.gitignore` | Blocks `.env` from git |

## Troubleshooting

**Auth failing?** Check `.env` and restart: `docker-compose restart`

**Service won't start?** Check logs: `docker-compose logs eddie-mcp`

**Port in use?** Change `PORT` in `.env` or kill process: `lsof -i :8000`

**API docs?** Open `http://localhost:8000/docs` when service is running