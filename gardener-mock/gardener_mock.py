from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.post("/generate")
async def generate(request: Request):
    """
    Mock endpoint to receive generation requests.
    Always returns HTTP 200 with a simple JSON response.
    """
    data = await request.json()
    print("Received generate request:", data)
    return JSONResponse(status_code=200, content={"status": "received"})
