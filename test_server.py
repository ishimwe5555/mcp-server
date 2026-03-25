#!/usr/bin/env python3
"""
Test script to verify the MCP server tools are exposed correctly.
"""
import inspect
import app as app_module


def main():
    """List all available tools in the server."""
    print("=" * 80)
    print("🚀 Eddie MCP Server - Tool Verification")
    print("=" * 80)
    print()
    
    # Dynamically find all functions decorated with @app.tool()
    custom_tools = []
    for name, obj in inspect.getmembers(app_module):
        if inspect.iscoroutinefunction(obj) and not name.startswith('_'):
            # Check if it's defined in the app module (not imported)
            if obj.__module__ == 'app':
                custom_tools.append((name, obj))
    
    # Sort by name for consistent output
    custom_tools.sort(key=lambda x: x[0])
    
    print(f"✅ Found {len(custom_tools)} tools registered:\n")
    
    # Group tools by category
    categories = {
        'AUTHENTICATION': [],
        'COLLECTIONS': [],
        'SEARCH & FEATURES': [],
        'USERS': [],
        'GROUPS': [],
        'STAC & CATALOG': []
    }
    
    for tool_name, tool_func in custom_tools:
        doc = tool_func.__doc__ or ""
        
        # Categorize based on function name
        if 'auth' in tool_name.lower():
            categories['AUTHENTICATION'].append((tool_name, tool_func))
        elif 'collection' in tool_name.lower():
            categories['COLLECTIONS'].append((tool_name, tool_func))
        elif 'search' in tool_name.lower() or 'feature' in tool_name.lower():
            categories['SEARCH & FEATURES'].append((tool_name, tool_func))
        elif 'user' in tool_name.lower():
            categories['USERS'].append((tool_name, tool_func))
        elif 'group' in tool_name.lower():
            categories['GROUPS'].append((tool_name, tool_func))
        else:
            categories['STAC & CATALOG'].append((tool_name, tool_func))
    
    # Print tools by category
    for category, tools in categories.items():
        if tools:
            print(f"\n{category}")
            print("-" * 80)
            
            for tool_name, tool_func in tools:
                print(f"\n  📌 {tool_name}")
                
                # Get first line of docstring
                if tool_func.__doc__:
                    doc_lines = tool_func.__doc__.strip().split('\n')
                    print(f"     {doc_lines[0]}")
                
                # Get parameters
                sig = inspect.signature(tool_func)
                params = {k: v for k, v in sig.parameters.items() if k not in ['self', 'cls']}
                
                if params:
                    print(f"     Parameters:")
                    for param_name, param in params.items():
                        annotation = param.annotation if param.annotation != inspect.Parameter.empty else "any"
                        if param.default != inspect.Parameter.empty:
                            if param.default is None:
                                print(f"       • {param_name}: {annotation} (optional)")
                            else:
                                print(f"       • {param_name}: {annotation} = {param.default}")
                        else:
                            print(f"       • {param_name}: {annotation} (required)")
    
    print()
    print("=" * 80)
    print(f"✅ Total: {len(custom_tools)} tools available for Eddie!")
    print("=" * 80)
    print()
    print("To start the MCP server, run:")
    print("  python app.py")
    print()
    print("Eddie can then connect and access all these tools.")


if __name__ == "__main__":
    main()
