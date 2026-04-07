import httpx
import os
from fastmcp import FastMCP
from typing import Optional, Dict, Any
from datetime import datetime, timedelta


app = FastMCP("eddie-mcp-server")

# Base URLs (configurable via environment variables)
EDITO_API_BASE = os.getenv("EDITO_API_BASE", "https://api.staging.edito.eu/data")
OAUTH2_TOKEN_URL = os.getenv("OAUTH2_TOKEN_URL", "https://auth.staging.edito.eu/auth/realms/datalab/protocol/openid-connect/token")

# Request timeout in seconds
REQUEST_TIMEOUT = 30

# OAuth2 credentials from environment
OAUTH2_CLIENT_ID = os.getenv("OAUTH2_CLIENT_ID")
OAUTH2_USERNAME = os.getenv("OAUTH2_USERNAME")
OAUTH2_PASSWORD = os.getenv("OAUTH2_PASSWORD")

# Token cache
_cached_token = None
_token_expires_at = None


async def get_oauth2_token() -> Optional[str]:
    """Get OAuth2 access token using password grant flow."""
    global _cached_token, _token_expires_at
    
    # Check if cached token is still valid
    if _cached_token and _token_expires_at:
        if datetime.now() < _token_expires_at:
            return _cached_token
    
    # Get new token if credentials are available
    if not OAUTH2_CLIENT_ID or not OAUTH2_USERNAME or not OAUTH2_PASSWORD:
        return None
    
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            data = {
                "client_id": OAUTH2_CLIENT_ID,
                "username": OAUTH2_USERNAME,
                "password": OAUTH2_PASSWORD,
                "grant_type": "password",
                "scope": "openid"
            }
            
            response = await client.post(OAUTH2_TOKEN_URL, data=data)
            response.raise_for_status()
            token_response = response.json()
            
            # Extract access token and expiration
            access_token = token_response.get("access_token")
            expires_in = token_response.get("expires_in", 3600)  # Default 1 hour
            
            if access_token:
                # Cache token with slight buffer (reduce by 5 minutes)
                _cached_token = access_token
                _token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                return access_token
            
            return None
    except Exception:
        return None


async def get_cached_token() -> Optional[str]:
    """Get cached authentication token, refreshing if expired."""
    return await get_oauth2_token()


def handle_error(error: Exception, context: str) -> Dict[str, Any]:
    """Format error responses consistently.
    
    Args:
        error: The exception that occurred
        context: Description of what was being attempted
    
    Returns:
        dict: Formatted error response
    """
    error_msg = str(error)
    
    if isinstance(error, httpx.HTTPStatusError):
        return {
            "error": True,
            "context": context,
            "status_code": error.response.status_code,
            "message": f"Edito API returned {error.response.status_code}: {error_msg}",
            "details": error.response.text[:500] if error.response.text else None
        }
    elif isinstance(error, httpx.ConnectError):
        return {
            "error": True,
            "context": context,
            "type": "CONNECTION_ERROR",
            "message": f"Failed to connect to Edito API: {error_msg}",
            "hint": "Check if the API is reachable"
        }
    elif isinstance(error, httpx.TimeoutException):
        return {
            "error": True,
            "context": context,
            "type": "TIMEOUT_ERROR",
            "message": f"Request timed out after {REQUEST_TIMEOUT} seconds",
            "hint": "Try with a smaller limit or simpler query"
        }
    else:
        return {
            "error": True,
            "context": context,
            "type": type(error).__name__,
            "message": error_msg
        }


# ============================================================================
# AUTHENTICATION TOOLS
# ============================================================================

@app.tool()
async def get_auth_token():
    """Get OAuth2 access token from the authentication server.
    
    If credentials are configured, fetches a fresh token from the OAuth2 endpoint.
    Token is cached for the duration of its validity.
    
    Returns:
        dict: Contains 'access_token' and token metadata
    """
    try:
        token = await get_oauth2_token()
        if token:
            return {
                "access_token": token,
                "token_type": "Bearer",
                "authenticated": True,
                "cached": True,
                "expires_at": _token_expires_at.isoformat() if _token_expires_at else None
            }
        else:
            return {
                "error": True,
                "message": "No credentials configured. Set OAUTH2_CLIENT_ID, OAUTH2_USERNAME, OAUTH2_PASSWORD in MCP config."
            }
    except Exception as e:
        return handle_error(e, "Getting OAuth2 token")


@app.tool()
async def check_auth_status():
    """Check if OAuth2 authentication is configured and valid.
    
    Returns:
        dict: Authentication status information
    """
    if not OAUTH2_CLIENT_ID or not OAUTH2_USERNAME or not OAUTH2_PASSWORD:
        return {
            "authenticated": False,
            "message": "Incomplete credentials. Configure OAUTH2_CLIENT_ID, OAUTH2_USERNAME, and OAUTH2_PASSWORD.",
            "configured": False
        }
    
    try:
        token = await get_oauth2_token()
        if token:
            return {
                "authenticated": True,
                "configured": True,
                "message": "Successfully authenticated with OAuth2",
                "token_cached": True,
                "token_expires_at": _token_expires_at.isoformat() if _token_expires_at else None
            }
        else:
            return {
                "authenticated": False,
                "configured": True,
                "message": "Failed to authenticate with provided OAuth2 credentials"
            }
    except Exception as e:
        return {
            "authenticated": False,
            "configured": True,
            "error": str(e)
        }


# ============================================================================
# COLLECTION TOOLS
# ============================================================================

@app.tool()
async def list_collections(limit: int = 50, offset: int = 0):
    """List all available collections in the EDITO catalog.
    
    Args:
        limit: Maximum number of collections to return (default: 50)
        offset: Number of results to skip for pagination (default: 0)
    
    Returns:
        dict: List of collection metadata and statistics
    """
    try:
        if limit < 1 or limit > 1000:
            return {"error": True, "message": "Limit must be between 1 and 1000"}
        if offset < 0:
            return {"error": True, "message": "Offset must be non-negative"}
            
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            params = {"limit": limit, "offset": offset}
            response = await client.get(f"{EDITO_API_BASE}/collections", params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, "Listing collections")


@app.tool()
async def get_collection_info(collection_id: str):
    """Get detailed information about a specific collection in EDITO.
    
    Args:
        collection_id: The ID of the collection
    
    Returns:
        dict: Collection metadata including statistics, extent, and description
    """
    try:
        if not collection_id or not collection_id.strip():
            return {"error": True, "message": "collection_id cannot be empty"}
            
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(f"{EDITO_API_BASE}/collections/{collection_id}")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, f"Getting collection info for {collection_id}")


# ============================================================================
# SEARCH & FEATURE TOOLS
# ============================================================================

@app.tool()
async def search_data(
    query: str,
    limit: int = 50,
    startIndex: int = 1,
    page: int = 1,
    collections: Optional[str] = None
):
    """Search for geospatial data across all collections using STAC search.
    
    Args:
        query: Search query string (free text search)
        limit: Maximum number of results to return (default: 50)
        startIndex: Index of the first result to return (default: 1)
        page: Page number for pagination (default: 1)
        collections: Comma-separated collection IDs to limit search
    
    Returns:
        dict: GeoJSON FeatureCollection with matching data items
    """
    try:
        if not query or not query.strip():
            return {"error": True, "message": "Search query cannot be empty"}
        if limit < 1 or limit > 1000:
            return {"error": True, "message": "Limit must be between 1 and 1000"}
        if startIndex < 1:
            return {"error": True, "message": "startIndex must be >= 1"}
        if page < 1:
            return {"error": True, "message": "page must be >= 1"}
            
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            params = {
                "q": query,
                "limit": limit,
                "startIndex": startIndex,
                "page": page,
            }
            if collections:
                params["collections"] = collections
                
            response = await client.get(f"{EDITO_API_BASE}/search", params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, f"Searching for '{query}'")


@app.tool()
async def search_collection_features(
    collection_id: str,
    query: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    bbox: Optional[str] = None
):
    """Search for features within a specific collection.
    
    Args:
        collection_id: The collection ID to search in
        query: Free text search query (optional)
        limit: Maximum number of results (default: 50)
        offset: Number of results to skip (default: 0)
        bbox: Bounding box in format 'minLon,minLat,maxLon,maxLat' (optional)
    
    Returns:
        dict: GeoJSON FeatureCollection with matching features
    """
    try:
        if not collection_id or not collection_id.strip():
            return {"error": True, "message": "collection_id cannot be empty"}
        if limit < 1 or limit > 1000:
            return {"error": True, "message": "Limit must be between 1 and 1000"}
        if offset < 0:
            return {"error": True, "message": "Offset must be non-negative"}
        
        # Validate bbox format if provided
        if bbox:
            bbox_parts = bbox.split(',')
            if len(bbox_parts) != 4:
                return {"error": True, "message": "bbox must be in format: minLon,minLat,maxLon,maxLat"}
            try:
                [float(b) for b in bbox_parts]
            except ValueError:
                return {"error": True, "message": "bbox values must be numbers"}
            
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            params = {"limit": limit, "offset": offset}
            if query:
                params["q"] = query
            if bbox:
                params["bbox"] = bbox
                
            response = await client.get(
                f"{EDITO_API_BASE}/collections/{collection_id}/items",
                params=params
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, f"Searching features in {collection_id}")


@app.tool()
async def get_feature_details(collection_id: str, feature_id: str):
    """Get detailed metadata for a specific feature in a collection.
    
    Args:
        collection_id: The collection ID containing the feature
        feature_id: The feature ID to retrieve
    
    Returns:
        dict: Complete feature metadata as GeoJSON
    """
    try:
        if not collection_id or not collection_id.strip():
            return {"error": True, "message": "collection_id cannot be empty"}
        if not feature_id or not feature_id.strip():
            return {"error": True, "message": "feature_id cannot be empty"}
            
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(
                f"{EDITO_API_BASE}/collections/{collection_id}/items/{feature_id}"
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, f"Getting feature {feature_id} from {collection_id}")


# ============================================================================
# USER TOOLS
# ============================================================================

@app.tool()
async def get_my_profile():
    """Get the authenticated user's own profile (requires authentication).
    
    Returns:
        dict: Current user profile information
    """
    try:
        token = await get_cached_token()
        if not token:
            return {
                "error": True,
                "message": "Not authenticated. Configure EDITO_USERNAME and EDITO_PASSWORD in MCP server config."
            }
        
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.get(f"{EDITO_API_BASE}/me", headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, "Getting authenticated user profile")


@app.tool()
async def get_user_profile(username: str):
    """Get profile information for a specific user.
    
    Args:
        username: The username to look up
    
    Returns:
        dict: User profile including id, picture, followers, and profile info
    """
    try:
        if not username or not username.strip():
            return {"error": True, "message": "username cannot be empty"}
        
        # Try with authentication first if available
        token = await get_cached_token()
        
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            
            response = await client.get(
                f"{EDITO_API_BASE}/users/{username}",
                headers=headers if headers else None
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, f"Getting profile for user '{username}'")


@app.tool()
async def get_users():
    """Get all users.
    
    Requires authentication for full access to user list.
    
    Returns:
        dict: List of users with their profile information
    """
    try:
        token = await get_cached_token()
        
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            
            response = await client.get(
                f"{EDITO_API_BASE}/users",
                headers=headers if headers else None
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, "Getting users list")


@app.tool()
async def get_user_features(username: str, limit: int = 50):
    """Get all features uploaded by a specific user.
    
    Args:
        username: The username whose features to retrieve
        limit: Maximum number of features to return (default: 50)
    
    Returns:
        dict: GeoJSON FeatureCollection of user's features (requires authentication)
    """
    try:
        if not username or not username.strip():
            return {"error": True, "message": "username cannot be empty"}
        if limit < 1 or limit > 1000:
            return {"error": True, "message": "Limit must be between 1 and 1000"}
        
        token = await get_cached_token()
        
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            
            params = {"limit": limit}
            response = await client.get(
                f"{EDITO_API_BASE}/users/{username}/features",
                params=params,
                headers=headers if headers else None
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, f"Getting features for user '{username}'")


# ============================================================================
# GROUP TOOLS
# ============================================================================

@app.tool()
async def list_groups(limit: int = 50):
    """List all available groups.
    
    Args:
        limit: Maximum number of groups to return (default: 50)
    
    Returns:
        dict: List of groups ordered by creation date
    """
    try:
        if limit < 1 or limit > 1000:
            return {"error": True, "message": "Limit must be between 1 and 1000"}
            
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            params = {"limit": limit}
            response = await client.get(f"{EDITO_API_BASE}/groups", params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, "Listing groups")


@app.tool()
async def get_group_info(group_name: str):
    """Get information about a specific group.
    
    Args:
        group_name: The name of the group
    
    Returns:
        dict: Group information including members and description
    """
    try:
        if not group_name or not group_name.strip():
            return {"error": True, "message": "group_name cannot be empty"}
            
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(f"{EDITO_API_BASE}/groups/{group_name}")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, f"Getting info for group '{group_name}'")


# ============================================================================
# STAC & CATALOG TOOLS
# ============================================================================

@app.tool()
async def get_stac_queryables():
    """Get available queryable properties for STAC API search filtering.
    
    Returns:
        dict: Schema of queryable fields that can be used for filtering
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(f"{EDITO_API_BASE}/queryables")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, "Getting STAC queryables")


@app.tool()
async def get_landing_page():
    """Get the Edito landing page with API endpoints and available resources.
    
    Returns:
        dict: Landing page with links to collections, search, and other endpoints
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(EDITO_API_BASE)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, "Getting landing page")


if __name__ == "__main__":
    app.run(transport="http", host="0.0.0.0", port=8000)

