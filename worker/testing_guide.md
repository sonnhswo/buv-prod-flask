# Developer Guide: Testing Background Document Ingestion

This guide outlines how to test the asynchronous document ingestion process end-to-end.

## 1. Prerequisites
- **Azure Storage Explorer** or Azure Portal access.
- **Azure Functions Core Tools** installed (`brew install azure-functions-core-tools@4`).
- A running **PostgreSQL** instance with the `ingestion_task` table (already applied via migrations).

## 2. Infrastructure Setup
1. Open your Azure Storage Account (`buvstorageuat`).
2. Navigate to **Queues**.
3. Create a new queue named: `document-ingestion-queue`.

## 3. Local Configuration

### Flask API ([.env](.env))
Ensure your `.env` has the correct `BLOB_CONN_STRING` (which is also used for the queue).

### Azure Function Worker ([worker/local.settings.json](worker/local.settings.json))
The worker needs access to your Storage and Database. Ensure `worker/local.settings.json` looks like this:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true", 
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsFeatureFlags": "EnableWorkerIndexing"
  }
}
```
> [!IMPORTANT]
> Change `AzureWebJobsStorage` to your actual Azure Storage Connection String to test against the real queue.

## 4. Running the Services

### Step A: Start the Flask API
**Using uv:**
```bash
uv run manage.py
```
**Using pip/venv:**
```bash
source .venv/bin/activate  # or venv\Scripts\activate on Windows
python manage.py
```

### Step B: Start the Background Worker
Open a new terminal:
```bash
# Ensure dependencies are installed
# Using uv: uv pip install -r requirements.txt
# Using pip: pip install -r requirements.txt

cd worker
func start
```

## 5. Testing the Flow

### Step 1: Upload a Document
Use Postman or curl to upload a file to a chatbot:
**Endpoint**: `POST /admin/chatbots/CB001/files`
**Payload**: `multipart/form-data` with a `file` field.

**Expected Result**:
- HTTP `202 Accepted` response.
- JSON body containing `"task_id": <ID>`.
- A new record in the `ingestion_task` table with status `PENDING`.

### Step 2: Observe the Queue
Check Azure Storage Explorer. You should briefly see a message in `document-ingestion-queue` with the task metadata.

### Step 3: Observe the Worker
The `func start` terminal should show logs:
- `Processing ingestion task <ID>...`
- `Update status to PROCESSING`
- (Detailed ingestion steps from langchain...)
- `Successfully completed ingestion task <ID>`

### Step 4: Poll for Status
**Endpoint**: `GET /admin/chatbots/CB001/tasks/<task_id>`

**Expected Result**:
- Initially: `{"status": "PENDING"}` or `{"status": "PROCESSING"}`.
- Finally: `{"status": "COMPLETED"}`.

### Step 5: Verify Final Ingestion
- Check **Azure AI Search** to ensure the new chunks were uploaded.
- Check the database `document` table to see the file record.

## 6. Troubleshooting
- **Missing Dependencies**: Run `pip install -r worker/requirements.txt` inside the worker environment.
- **Queue Connection**: If the worker doesn't pick up messages, verify the `connection="AzureWebJobsStorage"` string inside `worker/function_app.py` matches the key in `local.settings.json`.
- **DB Context**: If the worker fails with "Working outside of application context", ensure `sys.path` in `worker/function_app.py` is correctly resolving to the project root.
