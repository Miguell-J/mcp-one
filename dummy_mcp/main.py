# mcp_dummy/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict

app = FastAPI(title="MCP Dummy Server")

class ToolInfo(BaseModel):
    name: str
    description: str

class CallRequest(BaseModel):
    tool: str
    arguments: Dict[str, str]

TOOLS = [
    ToolInfo(name="say_hello", description="Returns a greeting"),
    ToolInfo(name="add_numbers", description="Adds two numbers")
]

@app.get("/tools", response_model=List[ToolInfo])
async def list_tools():
    return TOOLS

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/call")
async def call_tool(req: CallRequest):
    if req.tool == "say_hello":
        return {"success": True, "result": {"message": "Hello from Dummy!"}}
    elif req.tool == "add_numbers":
        a = int(req.arguments.get("a", 0))
        b = int(req.arguments.get("b", 0))
        return {"success": True, "result": {"sum": a+b}}
    return {"success": False, "error": "Tool not found"}
