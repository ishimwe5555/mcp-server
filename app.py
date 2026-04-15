import httpx
import os
from fastmcp import FastMCP
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

app = FastMCP("eddie-mcp-server")

# ============================================================================
# CONFIGURATION
# ============================================================================

# Base URL (configurable via environment variable)
EDITO_API_BASE = os.getenv("EDITO_API_BASE", "https://api.staging.edito.eu/data")

# Request timeout in seconds
REQUEST_TIMEOUT = 30

# Global user tracking - stores the currently authenticated user ID
_current_user_id: Optional[str] = None


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

class SessionTokenStore:
    """Per-user token storage with expiration tracking."""
    
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
    
    def set_token(self, user_id: str, token: str, expires_at: datetime) -> None:
        """Store token for a user."""
        self._sessions[user_id] = {
            "token": token,
            "expires_at": expires_at,
            "created_at": datetime.now()
        }
    
    def get_token(self, user_id: str) -> Optional[str]:
        """Retrieve token if still valid."""
        if user_id not in self._sessions:
            return None
        
        session = self._sessions[user_id]
        token = session.get("token")
        expires_at = session.get("expires_at")
        
        # Check if token is still valid
        if token and expires_at and datetime.now() < expires_at:
            return token
        
        return None
    
    def clear_session(self, user_id: str) -> None:
        """Clear a user's session and token."""
        if user_id in self._sessions:
            del self._sessions[user_id]


# Global session store
_session_store = SessionTokenStore()


# ============================================================================
# AUTHENTICATION & ERROR HANDLING
# ============================================================================

def extract_user_id_from_token(token: str) -> Optional[str]:
    """Extract user ID from JWT token's 'sub' claim.
    
    Args:
        token: JWT access token
    
    Returns:
        User ID from token's 'sub' claim, or None if unable to extract
    """
    try:
        import json
        import base64
        
        # JWT format: header.payload.signature
        parts = token.split('.')
        if len(parts) != 3:
            return None
        
        # Decode payload (add padding if needed)
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding
        
        decoded = base64.urlsafe_b64decode(payload)
        data = json.loads(decoded)
        
        # Extract user ID from common JWT claims
        return data.get('sub') or data.get('preferred_username') or data.get('email')
    except Exception:
        return None


async def initialize_session_token(user_id: str, token: str) -> None:
    """Store a validated token for a user.
    
    Args:
        user_id: User identifier from token
        token: Valid OAuth2 access token
    """
    # Assume token is valid for 1 hour if not otherwise specified
    expires_at = datetime.now() + timedelta(hours=1)
    _session_store.set_token(user_id, token, expires_at)


async def get_cached_token() -> Optional[str]:
    """Get cached authentication token for current user.
    
    Returns the token if it's still valid, None otherwise.
    """
    global _current_user_id
    if not _current_user_id:
        return None
    
    return _session_store.get_token(_current_user_id)


async def refresh_token(token: str, expires_in: int = 3600) -> None:
    """Refresh/update the token for current user.
    
    Args:
        token: New access token
        expires_in: Token TTL in seconds (default: 1 hour)
    """
    global _current_user_id
    if not _current_user_id:
        raise ValueError("No user authenticated")
    
    expires_at = datetime.now() + timedelta(seconds=expires_in - 300)  # 5 min buffer
    _session_store.set_token(_current_user_id, token, expires_at)


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
# ROUTES & SESSION MANAGEMENT
# ============================================================================

@app.custom_route("/health", methods=["GET"])
async def health(request):
    """Health check endpoint."""
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "healthy"})


@app.custom_route("/tools", methods=["GET"])
async def list_tools_endpoint(request):
    """List all available MCP tools with their descriptions."""
    from starlette.responses import JSONResponse
    import service
    import inspect
    
    tools_info = []
    
    # Get all functions from service module that are decorated with @app.tool()
    for name, obj in inspect.getmembers(service):
        if inspect.iscoroutinefunction(obj) and not name.startswith('_'):
            tools_info.append({
                "name": name,
                "description": (obj.__doc__ or "No description available").split('\n')[0]
            })
    
    return JSONResponse({
        "count": len(tools_info),
        "tools": sorted(tools_info, key=lambda x: x["name"])
    })


# ============================================================================
# SESSION-BASED AUTHENTICATION TOOLS
# ============================================================================

@app.tool()
async def init_session(access_token: str) -> Dict[str, Any]:
    """Initialize a new session with a user's OAuth2 access token.
    
    **CALL THIS FIRST** - validates and stores the access token for all subsequent API calls.
    
    The token is validated immediately by making a test call to the API. Once validated,
    all subsequent tool calls will use this token automatically.
    
    Typical flow:
    1. User obtains their access token from OAuth2 provider
    2. Call init_session with that token
    3. All subsequent tool calls will use this token
    
    Args:
        access_token: Valid OAuth2 access token for the EDITO API
    
    Returns:
        dict: Session initialization status with user information
    """
    global _current_user_id
    try:
        # Extract user ID from token
        user_id = extract_user_id_from_token(access_token)
        if not user_id:
            return {
                "success": False,
                "error": True,
                "message": "Could not extract user ID from token",
                "details": "The token format is invalid or missing required claims"
            }
        
        # Validate the token by making a test call
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            headers = {"Authorization": f"Bearer {access_token}"}
            response = await client.get(f"{EDITO_API_BASE}/me", headers=headers)
            response.raise_for_status()
            user_info = response.json()
        
        # Token is valid, store it and set current user
        await initialize_session_token(user_id, access_token)
        _current_user_id = user_id
        
        return {
            "success": True,
            "user_id": user_id,
            "user_info": user_info,
            "message": f"Session initialized for user {user_id}. All subsequent API calls will use this token.",
            "note": "Token automatically used by all tools until expired or replaced"
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            return {
                "success": False,
                "error": True,
                "message": f"Token validation failed (HTTP {e.response.status_code})",
                "details": "The provided token is invalid, expired, or lacks required permissions",
                "suggested_action": "Verify the token and try again with a valid OAuth2 access token"
            }
        return handle_error(e, "Initializing session")
    except Exception as e:
        return handle_error(e, "Initializing session")


@app.tool()
async def check_session_auth() -> Dict[str, Any]:
    """Check if current session has a valid authentication token.
    
    Returns:
        dict: Current session auth status
    """
    global _current_user_id
    try:
        token = await get_cached_token()
        
        if token and _current_user_id:
            return {
                "authenticated": True,
                "user_id": _current_user_id,
                "has_token": True,
                "message": "Session has valid authentication token"
            }
        elif _current_user_id:
            return {
                "authenticated": False,
                "user_id": _current_user_id,
                "has_token": False,
                "message": "Session exists but token is expired. Call init_session with a fresh token."
            }
        else:
            return {
                "authenticated": False,
                "user_id": None,
                "has_token": False,
                "message": "No session initialized. Call init_session first."
            }
    except Exception as e:
        return handle_error(e, "Checking session authentication")


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
        dict: Summarized collection metadata - total count, and slim collection list
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
            data = response.json()

        # Extract top-level total from links
        total_matched = None
        for link in data.get("links", []):
            if link.get("rel") == "items" and "matched" in link:
                total_matched = link["matched"]
                break

        # Slim down each collection: drop verbose description, keep essentials
        slim_collections = []
        for link in data.get("links", []):
            if link.get("rel") != "child":
                continue
            slim_collections.append({
                "title": link.get("title"),
                "id": link.get("href", "").split("/collections/")[-1],
                "matched": link.get("matched"),
                "description": (link.get("description") or "")[:120].rstrip() + "…"
                    if link.get("description") else None,
            })

        return {
            "total_collections": total_matched,
            "returned": len(slim_collections),
            "offset": offset,
            "collections": slim_collections,
        }

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
                "message": "Not authenticated. Call init_session first with a valid OAuth2 access token."
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