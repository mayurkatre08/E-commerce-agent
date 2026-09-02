# E-Commerce Support Agent

An agentic customer-support application for an e-commerce store. It combines a FastAPI backend, Streamlit chat UI, LangGraph routing, Groq LLM responses, MCP tools, SQLite order data, and ChromaDB policy retrieval.

## Features

- Answers questions about returns, exchanges, shipping, sizing, payments, and cancellations using policy documents.
- Looks up orders with optional customer ownership verification.
- Cancels eligible orders and changes sizes for orders that are still processing.
- Escalates complex or unresolved requests to a human support ticket.
- Exposes runtime metrics and optional LangSmith tracing.

## Architecture

```text
Streamlit UI
    |
    v
FastAPI (/chat, /order, /metrics, /health)
    |
    v
LangGraph supervisor -> RAG, order, action, or escalation agent
    |
    v
MCP client --stdio--> MCP server
                         |-- ChromaDB policy search
                         |-- SQLite order tools
```

The FastAPI lifespan starts the MCP server as a subprocess and loads its tools automatically. You do not need to start the MCP server separately when using the API.

## Requirements

- Python 3.10 or newer
- A Groq API key
- Windows, macOS, or Linux

## Setup

From this directory:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On macOS or Linux, activate the environment with:

```bash
source .venv/bin/activate
```

Create the environment file:

```powershell
Copy-Item .env.example .env
```

Set at least `GROQ_API_KEY` in `.env`. The default model is configured by `GROQ_MODEL` and can be changed there. LangSmith variables are optional and enable tracing when valid credentials are supplied.

## Initialize Data

Seed the SQLite database and build the ChromaDB policy index:

```powershell
python data/seed_db.py
python vectorstore/ingest.py
```

Run these commands again whenever you want to reset the sample orders or rebuild the policy index.

## Run the Application

Start the API from the project directory:

```powershell
uvicorn api.main:app --reload --port 8000
```

In a second terminal, activate the same virtual environment and start the UI:

```powershell
streamlit run ui/app.py
```

Open the Streamlit URL shown in the terminal, usually `http://localhost:8501`. The UI expects the API at `http://localhost:8000`; change `API_URL` in `ui/app.py` if the API uses another address.

## API Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check API and graph readiness |
| `POST` | `/chat` | Run one support conversation turn |
| `GET` | `/order/{order_id}` | Look up an order directly |
| `GET` | `/metrics` | Get observability metrics |

Example chat request:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/chat `
  -ContentType 'application/json' `
  -Body '{"message":"Where is my order?","customer_id":"C001","order_id":"ORD9001"}'
```

The seeded database includes predictable examples such as `ORD9001` for customer `C001` and `ORD9002` for customer `C002`.

## MCP Tools

The MCP server exposes five tools:

- `policy_search`
- `get_order`
- `cancel_order`
- `change_size`
- `escalate_to_human`

Order mutations verify the customer ID. Cancellation and size changes are only allowed while an order has `processing` status.

## Tests

Run the full test suite from this directory:

```powershell
pytest -q
```

The tests cover the seeded data and the project phases, including MCP tools, MCP client connectivity, LangGraph execution, observability, and API behavior.

## Project Layout

```text
agents/          Supervisor and specialist agent nodes
api/             FastAPI application
 data/           Database seeding and policy documents
db/              SQLite database created by the seed script
graph/           LangGraph workflow definition
mcp_client/      MCP stdio client adapter
mcp_server/      FastMCP tool server
observability/   Metrics and optional LangSmith tracing
tests/           Automated tests
ui/              Streamlit interface
vectorstore/     ChromaDB ingestion and local index
```

## Security Notes

- Keep `.env` private and never commit API keys.
- The included customer and order records are dummy data for local development.
- `allow_origins=["*"]` is configured for local development in the FastAPI app; restrict it before deploying publicly.
