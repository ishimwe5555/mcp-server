"""
HTTP wrapper for Eddie MCP Server - exposes MCP tools via REST API
Allows Intercom agent to call geospatial data tools via HTTP
"""
import asyncio
import os
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import logging

from app import (
    get_auth_token,
    check_auth_status,
    list_collections,
    get_collection_info,
    search_data,
    search_collection_features,
    get_feature_details,
    get_my_profile,
    get_user_profile,
    get_users,
    get_user_features,
    list_groups,
    get_group_info,
    get_stac_queryables,
    get_landing_page,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
api = FastAPI(
    title="Eddie MCP Service API",
    description="REST API wrapper for Eddie MCP Server geospatial tools",
    version="1.0.0"
)

# Add CORS middleware
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to Intercom domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class ToolRequest(BaseModel):
    """Generic tool request"""
    parameters: Dict[str, Any] = {}

class ToolResponse(BaseModel):
    """Generic tool response"""
    success: bool
    tool: str
    result: Dict[str, Any]
    error: Optional[str] = None

# Map tool names to their async functions
TOOLS_MAP = {
    # Authentication
    "get_auth_token": get_auth_token,
    "check_auth_status": check_auth_status,
    # Collections
    "list_collections": list_collections,
    "get_collection_info": get_collection_info,
    "search_collection_features": search_collection_features,
    # Search & Features
    "search_data": search_data,
    "get_feature_details": get_feature_details,
    # Users
    "get_my_profile": get_my_profile,
    "get_user_profile": get_user_profile,
    "get_users": get_users,
    "get_user_features": get_user_features,
    # Groups
    "list_groups": list_groups,
    "get_group_info": get_group_info,
    # STAC & Catalog
    "get_stac_queryables": get_stac_queryables,
    "get_landing_page": get_landing_page,
}

# ============================================================================
# HEALTH & INFO ENDPOINTS
# ============================================================================

@api.get("/health", tags=["Health"])
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Eddie MCP Service",
        "version": "1.0.0"
    }

@api.get("/tools", tags=["Info"])
async def list_tools():
    """List all available tools"""
    return {
        "tools": list(TOOLS_MAP.keys()),
        "count": len(TOOLS_MAP),
        "categories": {
            "authentication": ["get_auth_token", "check_auth_status"],
            "collections": ["list_collections", "get_collection_info", "search_collection_features"],
            "search": ["search_data", "get_feature_details"],
            "users": ["get_my_profile", "get_user_profile", "get_users", "get_user_features"],
            "groups": ["list_groups", "get_group_info"],
            "catalog": ["get_stac_queryables", "get_landing_page"],
        }
    }

# ============================================================================
# TOOL EXECUTION ENDPOINTS
# ============================================================================

@api.post("/tools/{tool_name}", response_model=ToolResponse, tags=["Tools"])
async def execute_tool(tool_name: str, request: ToolRequest) -> ToolResponse:
    """
    Execute an MCP tool by name with the provided parameters.
    
    **Tool Categories:**
    - **authentication**: Token management
    - **collections**: Browse and manage collections
    - **search**: Query geospatial features
    - **users**: User information and datasets
    - **groups**: User groups management
    - **catalog**: STAC resources
    """
    if tool_name not in TOOLS_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found. Available tools: {list(TOOLS_MAP.keys())}"
        )
    
    try:
        tool_func = TOOLS_MAP[tool_name]
        logger.info(f"Executing tool: {tool_name} with params: {request.parameters}")
        
        # Execute the tool with provided parameters
        result = await tool_func(**request.parameters)
        
        # Check if result contains an error
        is_error = isinstance(result, dict) and result.get("error", False)
        
        return ToolResponse(
            success=not is_error,
            tool=tool_name,
            result=result,
            error=result.get("message") if is_error else None
        )
    
    except TypeError as e:
        logger.error(f"Invalid parameters for {tool_name}: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid parameters for tool '{tool_name}': {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error executing {tool_name}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error executing tool '{tool_name}': {str(e)}"
        )

# ============================================================================
# HELPER ENDPOINTS (Convenience routes for common operations)
# ============================================================================

@api.post("/search", tags=["Convenience"])
async def search(query: str, limit: int = 10, collections: Optional[str] = None):
    """
    Quick search endpoint - searches across collections
    
    Args:
        query: Search query string
        limit: Max results (default: 10)
        collections: Comma-separated collection IDs (optional)
    """
    try:
        result = await search_data(query=query, limit=limit, collections=collections)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api.get("/collections", tags=["Convenience"])
async def get_collections(limit: int = 50, offset: int = 0):
    """Quick collections list endpoint"""
    try:
        result = await list_collections(limit=limit, offset=offset)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api.get("/collections/{collection_id}", tags=["Convenience"])
async def get_collection(collection_id: str):
    """Quick collection details endpoint"""
    try:
        result = await get_collection_info(collection_id=collection_id)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# AUTHENTICATION CHECK
# ============================================================================

@api.get("/auth/status", tags=["Health"])
async def auth_status():
    """Check authentication status"""
    try:
        result = await check_auth_status()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# STARTUP/SHUTDOWN
# ============================================================================

@api.on_event("startup")
async def startup_event():
    logger.info("Eddie MCP Service starting up...")
    status = await check_auth_status()
    if status.get("authenticated"):
        logger.info("✓ OAuth2 authentication configured and working")
    else:
        logger.warning("✗ OAuth2 authentication not configured - some features may be limited")

@api.on_event("shutdown")
async def shutdown_event():
    logger.info("Eddie MCP Service shutting down...")

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    logger.info(f"Starting Eddie MCP Service on {host}:{port}")
    
    uvicorn.run(
        "service:api",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )
