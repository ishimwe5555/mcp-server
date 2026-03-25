# Eddie MCP Server - Resto API Integration

A Model Context Protocol (MCP) server that exposes the Resto geospatial data API as tools for the Eddie agent.

## Overview

This server provides access to different tools across the categories below:

- **Authentication**: Token management
- **Collections**: Browse and manage geospatial data collections
- **Search & Features**: Query and retrieve geospatial features
- **Users**: Access user profiles and datasets
- **Groups**: Manage user groups
- **STAC & Catalog**: Explore STAC resources

## Features

✅ **Comprehensive Error Handling**
- HTTP error detection (4xx, 5xx)
- Connection error handling
- Request timeout protection (30s)
- Input validation for all parameters
- Detailed error messages for debugging

✅ **Robust Implementation**
- Async/await for non-blocking operations
- Parameter validation (ranges, formats)
- Structured error responses
- Consistent API across all tools

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Local Testing

Start the server:
```bash
python app.py
```

Verify tools are exposed:
```bash
python test_server.py
```

### Integration with Eddie

Configure the connection:

```json
{
  "mcpServers": {
    "eddie-resto": {
      "command": "python",
      "args": ["/path/to/app.py"],
      "env": {}
    }
  }
}
```

## Tools Reference

### Authentication
- **get_auth_token**: Get fresh authentication token

### Collections
- **list_collections**: List all collections with pagination
- **get_collection_info**: Get detailed collection metadata
- **get_user_collections**: Get collections owned by a user
- **search_collection_features**: Search features in a specific collection

### Search & Features
- **search_data**: Global search across all collections
- **get_feature_details**: Get specific feature metadata
- **get_user_features**: Get features uploaded by a user

### Users
- **get_user_profile**: Get user profile information

### Groups
- **list_groups**: List all available groups
- **get_group_info**: Get specific group information

### STAC & Catalog
- **get_stac_queryables**: Get available query filters
- **get_landing_page**: Get API landing page

## Error Handling

All tools return structured error responses:

```python
{
  "error": True,
  "context": "What was being attempted",
  "status_code": 404,  # If HTTP error
  "message": "Human-readable error message",
  "details": "Raw response text (if applicable)"
}
```

### Error Types

- **HTTP Errors**: Include status code and response details
- **Connection Errors**: Network unavailable or DNS resolution failed
- **Timeout Errors**: Request exceeded 30-second limit
- **Validation Errors**: Invalid input parameters

### Input Validation

The server validates all parameters:
- Non-empty strings (usernames, collection IDs, etc.)
- Limit ranges (1-1000)
- Non-negative offsets
- Bbox format: `minLon,minLat,maxLon,maxLat`

## Development

### Adding New Tools

1. Add a new async function decorated with `@app.tool()`
2. Include comprehensive docstring
3. Wrap in try/except with `handle_error()`
4. Validate inputs before API calls
5. Test with `python test_server.py`

Example:
```python
@app.tool()
async def my_tool(param: str) -> dict:
    """Short description.
    
    Args:
        param: Parameter description
    
    Returns:
        dict: Response description
    """
    try:
        if not param or not param.strip():
            return {"error": True, "message": "param cannot be empty"}
        
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(f"{RESTO_API_BASE}/endpoint", params={})
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, "Doing something")
```

## Configuration

- **API Base**: `https://api.staging.edito.eu/data`
- **Request Timeout**: 30 seconds
- **Max Limit**: 1000 items per request
- **Connection Pool**: Reused per request (async context manager)

## Troubleshooting

**"Failed to connect to resto API"**
- Check API URL is reachable: `curl https://api.staging.edito.eu/data/`
- Check your network connection

**"Request timed out"**
- API is slow or overloaded
- Try with `limit=1` to test connectivity
- Reduce query complexity

**"API returned 404"**
- Resource doesn't exist
- Check collection/feature ID is correct
- Use `list_collections()` to find valid IDs

**"API returned 401/403"**
- Authentication required
- Use `get_auth_token()` first
- May need valid credentials for some endpoints
