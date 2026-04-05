"""
Minimal MCP Client - Demonstrates the Full MCP Protocol Flow

This script shows what MCP actually does:
1. Spawns the MCP server as a subprocess
2. Performs protocol handshake (initialize)
3. Discovers available tools (tools/list)
4. Calls a tool (tools/call)
5. Receives structured response

Run this INSTEAD of test_classifier.py to see real MCP in action.

Usage:
    python mcp_client_demo.py
"""

import asyncio
import json
import sys
from contextlib import asynccontextmanager

# MCP SDK imports
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ============================================================================
# Configuration
# ============================================================================

# Path to your MCP server module
SERVER_MODULE = "button_classifier.server"


# ============================================================================
# MCP Client Demo
# ============================================================================

async def run_mcp_demo():
    """Demonstrate the full MCP protocol flow."""
    
    print("=" * 70)
    print("  MCP CLIENT DEMO - See the Protocol in Action")
    print("=" * 70)
    
    # -------------------------------------------------------------------------
    # Step 1: Define server parameters
    # -------------------------------------------------------------------------
    print("\n📋 STEP 1: Define Server Parameters")
    print("-" * 50)
    
    server_params = StdioServerParameters(
        command=sys.executable,  # Current Python interpreter
        args=["-m", SERVER_MODULE],
        env=None  # Inherit environment
    )
    
    print(f"   Command: {server_params.command}")
    print(f"   Args: {server_params.args}")
    print(f"   Transport: stdio (stdin/stdout pipes)")
    
    # -------------------------------------------------------------------------
    # Step 2: Connect to server (spawns subprocess)
    # -------------------------------------------------------------------------
    print("\n🚀 STEP 2: Spawn Server & Connect")
    print("-" * 50)
    print("   Starting MCP server as subprocess...")
    
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            
            # -----------------------------------------------------------------
            # Step 3: Initialize (MCP handshake)
            # -----------------------------------------------------------------
            print("\n🤝 STEP 3: Protocol Handshake (initialize)")
            print("-" * 50)
            
            init_result = await session.initialize()
            
            print(f"   Server name: {init_result.serverInfo.name}")
            print(f"   Protocol version: {init_result.protocolVersion}")
            print(f"   Capabilities: {init_result.capabilities}")
            
            # -----------------------------------------------------------------
            # Step 4: Discover tools (tools/list)
            # -----------------------------------------------------------------
            print("\n🔍 STEP 4: Discover Available Tools (tools/list)")
            print("-" * 50)
            
            tools_response = await session.list_tools()
            
            print(f"   Found {len(tools_response.tools)} tool(s):\n")
            
            for tool in tools_response.tools:
                print(f"   📦 Tool: {tool.name}")
                print(f"      Description: {tool.description[:80]}...")
                if tool.inputSchema:
                    props = tool.inputSchema.get("properties", {})
                    print(f"      Parameters: {list(props.keys())}")
                print()
            
            # -----------------------------------------------------------------
            # Step 5: Call health_check tool
            # -----------------------------------------------------------------
            print("\n💓 STEP 5: Call Tool (health_check)")
            print("-" * 50)
            
            health_result = await session.call_tool("health_check", {})
            
            print("   Request: tools/call 'health_check' {}")
            print(f"   Response:")
            
            # Parse and pretty-print the response
            for content in health_result.content:
                if content.type == "text":
                    parsed = json.loads(content.text)
                    print(json.dumps(parsed, indent=6))
            
            # -----------------------------------------------------------------
            # Step 6: Call classify_buttons tool
            # -----------------------------------------------------------------
            print("\n🎯 STEP 6: Call Tool (classify_buttons)")
            print("-" * 50)
            
            test_input = {
                "params": {
                    "buttons": [
                        "Sign up",
                        "Deals of the Day",
                        "Create account",
                        "FAQ",
                        "Start free trial"
                    ],
                    "target_action": "signup",
                    "site_context": "Demo ecommerce site"
                }
            }
            
            print(f"   Request: tools/call 'classify_buttons'")
            print(f"   Input: {json.dumps(test_input, indent=6)}")
            print("\n   Waiting for LLM response...")
            
            classify_result = await session.call_tool("classify_buttons", test_input)
            
            print("\n   Response:")
            print(f"   Content items: {len(classify_result.content)}")
            
            for i, content in enumerate(classify_result.content):
                print(f"\n   Content[{i}] type: {content.type}")
                
                if content.type == "text":
                    raw_text = content.text
                    print(f"   Raw text length: {len(raw_text) if raw_text else 0}")
                    
                    if not raw_text:
                        print("   ⚠️  Empty response text!")
                        continue
                    
                    # Show first 200 chars for debugging
                    print(f"   Raw text preview: {raw_text[:200]}...")
                    
                    try:
                        parsed = json.loads(raw_text)
                        
                        # Check for error in response
                        if "error" in parsed:
                            print(f"\n   ⚠️  Server returned error: {parsed['error']}")
                            continue
                        
                        # Pretty print results
                        print("\n   Results:")
                        print("   " + "-" * 46)
                        for r in parsed.get("results", []):
                            score = r["score"]
                            indicator = "✅" if score >= 5 else "❌" if score <= -5 else "➖"
                            print(f"   {indicator} [{score:+3d}] {r['text']:25s} | {r['reason']}")
                        print("   " + "-" * 46)
                        print(f"   Recommended: {parsed.get('recommended', 'None')}")
                        print(f"   Confidence: {parsed.get('confidence', 'unknown')}")
                        print(f"   Model: {parsed.get('model_used', 'unknown')}")
                        
                    except json.JSONDecodeError as e:
                        print(f"   ⚠️  JSON parse error: {e}")
                        print(f"   Raw content: {repr(raw_text[:500])}")
                else:
                    print(f"   Non-text content: {content}")
    
    # -------------------------------------------------------------------------
    # Step 7: Done (server subprocess terminated)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("✅ MCP Demo Complete!")
    print("=" * 70)
    print("""
What just happened:

1. We spawned button_classifier.server as a subprocess
2. Connected via stdio (stdin/stdout pipes)
3. Performed MCP handshake (initialize)
4. Discovered tools via MCP protocol (tools/list)
5. Called tools via MCP protocol (tools/call)
6. Server handled requests, called Ollama, returned results
7. Subprocess terminated when we exited the context

This is REAL MCP - not just "calling Ollama with extra steps"!

The server could be:
- A different language (TypeScript, Go)
- Running remotely (HTTP transport)
- Used by Claude Desktop
- Used by any MCP-compatible client

Your audit script will do exactly this, but integrated into the test flow.
""")


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    print("\n" + "🔧" * 35)
    print("  BUTTON CLASSIFIER - MCP PROTOCOL DEMO")
    print("🔧" * 35)
    
    try:
        asyncio.run(run_mcp_demo())
    except KeyboardInterrupt:
        print("\n\nDemo interrupted.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Is Ollama running? (ollama list)")
        print("  2. Is the package installed? (pip install -e .)")
        print("  3. Are you in the venv? (venv\\Scripts\\activate)")
        raise
