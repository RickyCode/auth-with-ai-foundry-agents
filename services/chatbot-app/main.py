from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
import os
import requests
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import dotenv
from fastapi import Request
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient

dotenv.load_dotenv()

KEYCLOAK_BASE_URL = os.getenv("KEYCLOACK_BASE_URL")
REALM_NAME = os.getenv("REALM_NAME")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

REDIRECT_URI = "http://localhost:5000/callback"

AUTH_URL = f"{KEYCLOAK_BASE_URL}/realms/{REALM_NAME}/protocol/openid-connect/auth"
TOKEN_URL = f"{KEYCLOAK_BASE_URL}/realms/{REALM_NAME}/protocol/openid-connect/token"

PROJECT_ENDPOINT = os.getenv("PROJECT_ENDPOINT")
BALANCE_AGENT_ID = os.getenv("BALANCE_AGENT_ID")

client = AgentsClient(
    endpoint=PROJECT_ENDPOINT,
    credential=DefaultAzureCredential()
)

app = FastAPI(title="POC Balance Chat")

app.add_middleware(
    SessionMiddleware,
    secret_key="cambiar-por-una-secret-key-segura",
)

@app.get("/")
async def home(request: Request):
    token = request.session.get("access_token")
    return {"logged_in": bool(token)}

@app.get("/login")
async def login():
    url = (
        f"{AUTH_URL}"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=openid"
    )
    return RedirectResponse(url)


@app.get("/callback")
async def callback(request: Request, code: str):
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    response = requests.post(TOKEN_URL, data=data, headers=headers)

    if response.status_code != 200:
        return JSONResponse(
            {"error": "token exchange failed", "details": response.text},
            status_code=400,
        )

    tokens = response.json()

    request.session["access_token"] = tokens["access_token"]

    return RedirectResponse(url="/")

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)

@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    user_message = body.get("message")

    if not user_message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    thread = client.threads.create()

    client.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message,
    )

    run = client.runs.create_and_process(
        thread_id=thread.id,
        agent_id=BALANCE_AGENT_ID,
    )

    if run.status != "completed":
        return JSONResponse(
            {"error": f"run failed: {run.status}"},
            status_code=500,
        )

    last_text = client.messages.get_last_message_text_by_role(
        thread_id=thread.id,
        role="assistant",
    )

    return {"response": last_text}