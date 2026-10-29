import os
import sys
from pathlib import Path

import certifi
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_groq import ChatGroq

# ==========================================
# Environment configuration
# ==========================================

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
AVIATION_STACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Automatically find the current project folder.
# This replaces the hard-coded Windows paths.
PROJECT_DIR = Path(__file__).resolve().parent
WEATHER_SERVER_PATH = PROJECT_DIR / "custom_weather_mcp_server.py"

# ==========================================
# LLM
# ==========================================

llm = ChatGroq(
    model="meta-llama/llama-prompt-guard-2-22m",
    api_key=GROQ_API_KEY
)

client = MultiServerMCPClient(
    {
       "tavily": {
            "transport": "streamable_http",
            "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}"
        },
       "aviationstack": {
            "transport": "stdio",
            "command": "uvx",
            "args": [
                "aviationstack-mcp"
            ],
            "env": { "API_KEY": AVIATION_STACK_API_KEY }
        },
        "weather": {
            "transport": "stdio",

            # Use the same Python environment that runs app.py.
            "command": fr"{PROJECT_DIR}\travel\Scripts\python.exe",

            # Automatically use custom_weather_mcp_server.py
            # from the current project directory.
            "args": [str(WEATHER_SERVER_PATH)],

            "env": {"OPENWEATHER_API_KEY":"OPENWEATHER_API_KEY"}
        }
    }
)

async def get_all_tools():
    tools = await client.get_tools()
    print("\nAvailable MCP Tools:\n")

    for tool in tools:
        print(tool.name)



search_tool = None
aviation_tools ={}

async def initialize_mcp():
    global search_tool 
    global aviation_tools
    if search_tool is not None and aviation_tools:
        return

    tools = await client.get_tools()
    print("\nAvailable MCP Tools:")

    for tool in tools:
        print(tool.name)

    search_tool = next(
        tool
        for tool in tools
        if tool.name == "tavily_search"
    )

    aviation_tools = {
         tool.name: tool
         for tool in tools
         if tool.name != "tavily_search"
    }   



# This function can be used to call the tavily_search tool with a query in backend.py
async def tavily_mcp_search(query: str):
    await initialize_mcp()

    result = await search_tool.ainvoke(
        {
            "query": query
        }
    )

    return result

async def aviation_mcp_call(
    tool_name: str,
    tool_args: dict = None
):
    # await initialize_mcp()

    # tool = aviation_tools.get(tool_name)

    # if tool is None:
    #     available_tools = ", ".join(
    #         sorted(aviation_tools.keys())
    #     )

    #     raise ValueError(
    #         f"AviationStack tool '{tool_name}' "
    #         "was not found. "
    #         f"Available tools: "
    #         f"{available_tools or 'none'}"
    #     )

    # result = await tool.ainvoke(
    #     tool_args or {}
    # )

    tools = await client.get_tools()

    tool = next(
           t for t in tool
           if t.name == tool_name
        )
    result = await tool.ainvoke(
        tool_args or {}
    )
    return result



# ==========================================
# Weather MCP tools
# ==========================================

weather_tool = None
forecast_tool = None

async def initialize_weather_tools():
    global weather_tool
    global forecast_tool

    if (
        weather_tool is not None
        and forecast_tool is not None
    ):
        return

    if not WEATHER_SERVER_PATH.exists():
        raise FileNotFoundError(
            "Weather MCP server file was not found: "
            f"{WEATHER_SERVER_PATH}"
        )

    # Load only Weather.
    # Tavily and AviationStack will not be started.
    tools = await client.get_tools(
        server_name="weather"
    )

    tools_by_name = {
        tool.name: tool
        for tool in tools
    }

    weather_tool = tools_by_name.get(
        "get_current_weather"
    )

    forecast_tool = tools_by_name.get(
        "get_forecast"
    )

    missing_tools = []

    if weather_tool is None:
        missing_tools.append(
            "get_current_weather"
        )

    if forecast_tool is None:
        missing_tools.append(
            "get_forecast"
        )

    # if missing_tools:
    #     available_tools = ", ".join(
    #         tools_by_name.keys()
    #     )

    #     raise RuntimeError(
    #         "Missing Weather MCP tools: "
    #         f"{', '.join(missing_tools)}. "
    #         f"Available tools: "
    #         f"{available_tools or 'none'}"
    #     )


async def weather_mcp_search(city: str):
    await initialize_weather_tools()

    result = await weather_tool.ainvoke(
        {
            "city": city
        }
    )

    return result

async def forecast_mcp_search(city: str):
    await initialize_weather_tools()

    result = await forecast_tool.ainvoke(
        {
            "city": city
        }
    )

    return result


# ==========================================
# Destination extractor
# ==========================================

def extract_destination(query: str):
    prompt = f"""
    Extract only the destination city or country.

    Query:
    {query}

    Return only destination name.
    """

    response = llm.invoke(prompt)

    return response.content.strip()