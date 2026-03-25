import httpx
from fastmcp import FastMCP
from typing import Optional, Dict, Any


app = FastMCP("eddie-resto-server")

# Base URL for the resto API
RESTO_API_BASE = "https://api.staging.edito.eu/data"

# Request timeout in seconds
REQUEST_TIMEOUT = 30


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
            "message": f"API returned {error.response.status_code}: {error_msg}",
            "details": error.response.text[:500] if error.response.text else None
        }
    elif isinstance(error, httpx.ConnectError):
        return {
            "error": True,
            "context": context,
            "type": "CONNECTION_ERROR",
            "message": f"Failed to connect to resto API: {error_msg}",
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
    """Get a fresh authentication token (rJWT) from the resto API.
    
    Returns:
        dict: Contains 'token' and 'profile' information
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(f"{RESTO_API_BASE}/auth")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, "Getting authentication token")


# ============================================================================
# COLLECTION TOOLS
# ============================================================================

@app.tool()
async def list_collections(limit: int = 50, offset: int = 0):
    """List all available collections in the resto catalog.
    
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
            response = await client.get(f"{RESTO_API_BASE}/collections", params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, "Listing collections")


@app.tool()
async def get_collection_info(collection_id: str):
    """Get detailed information about a specific collection in resto.
    
    Args:
        collection_id: The ID of the collection
    
    Returns:
        dict: Collection metadata including statistics, extent, and description
    """
    try:
        if not collection_id or not collection_id.strip():
            return {"error": True, "message": "collection_id cannot be empty"}
            
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(f"{RESTO_API_BASE}/collections/{collection_id}")
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
    limit: int = 10,
    offset: int = 0,
    collections: Optional[str] = None
):
    """Search for geospatial data across all collections using STAC search.
    
    Args:
        query: Search query string (free text search)
        limit: Maximum number of results to return (default: 10)
        offset: Number of results to skip for pagination (default: 0)
        collections: Comma-separated collection IDs to limit search
    
    Returns:
        dict: GeoJSON FeatureCollection with matching data items
    """
    try:
        if not query or not query.strip():
            return {"error": True, "message": "Search query cannot be empty"}
        if limit < 1 or limit > 1000:
            return {"error": True, "message": "Limit must be between 1 and 1000"}
        if offset < 0:
            return {"error": True, "message": "Offset must be non-negative"}
            
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            params = {
                "q": query,
                "limit": limit,
                "offset": offset,
            }
            if collections:
                params["collections"] = collections
                
            response = await client.get(f"{RESTO_API_BASE}/search", params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, f"Searching for '{query}'")


@app.tool()
async def search_collection_features(
    collection_id: str,
    query: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    bbox: Optional[str] = None
):
    """Search for features within a specific collection.
    
    Args:
        collection_id: The collection ID to search in
        query: Free text search query (optional)
        limit: Maximum number of results (default: 10)
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
                f"{RESTO_API_BASE}/collections/{collection_id}/items",
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
                f"{RESTO_API_BASE}/collections/{collection_id}/items/{feature_id}"
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, f"Getting feature {feature_id} from {collection_id}")


# ============================================================================
# USER TOOLS
# ============================================================================

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
            
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(f"{RESTO_API_BASE}/users/{username}")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, f"Getting profile for user '{username}'")


@app.tool()
async def get_user_collections(username: str, limit: int = 50):
    """Get all collections owned by a specific user.
    
    Args:
        username: The username whose collections to retrieve
        limit: Maximum number of collections to return (default: 50)
    
    Returns:
        dict: List of collections owned by the user
    """
    try:
        if not username or not username.strip():
            return {"error": True, "message": "username cannot be empty"}
        if limit < 1 or limit > 1000:
            return {"error": True, "message": "Limit must be between 1 and 1000"}
            
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            params = {"limit": limit}
            response = await client.get(
                f"{RESTO_API_BASE}/users/{username}/collections",
                params=params
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, f"Getting collections for user '{username}'")


@app.tool()
async def get_user_features(username: str, limit: int = 50):
    """Get all features uploaded by a specific user.
    
    Args:
        username: The username whose features to retrieve
        limit: Maximum number of features to return (default: 50)
    
    Returns:
        dict: GeoJSON FeatureCollection of user's features
    """
    try:
        if not username or not username.strip():
            return {"error": True, "message": "username cannot be empty"}
        if limit < 1 or limit > 1000:
            return {"error": True, "message": "Limit must be between 1 and 1000"}
            
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            params = {"limit": limit}
            response = await client.get(
                f"{RESTO_API_BASE}/users/{username}/features",
                params=params
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
            response = await client.get(f"{RESTO_API_BASE}/groups", params=params)
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
            response = await client.get(f"{RESTO_API_BASE}/groups/{group_name}")
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
            response = await client.get(f"{RESTO_API_BASE}/queryables")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, "Getting STAC queryables")


@app.tool()
async def get_landing_page():
    """Get the resto landing page with API endpoints and available resources.
    
    Returns:
        dict: Landing page with links to collections, search, and other endpoints
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(RESTO_API_BASE)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return handle_error(e, "Getting landing page")


if __name__ == "__main__":
    app.run()
