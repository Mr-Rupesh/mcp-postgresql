# mcp-postgres-qa

Ask questions about a postgres database in plain english. An MCP server exposes
the db as tools, and a langgraph agent figures out which tools to call. 
3 tools planned.
- list_tables
- get_schema
- run_query


Stack: python, MCP, langgraph, postgres, psycopg2, docker.

## why

Wanted to learn the MCP protocol hands on, and build something that actually
enforces safety instead of just hoping the llm writes good sql. The safety
rails here are hard constraints at the db level, not prompts.

## Flow

user question -&gt; langgraph agent -&gt; MCP server (stdio) -&gt; postgres
