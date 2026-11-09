from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from .models import TaskIn, TaskPatch, PlanIn, ChatIn
from .store import Store
from .agent import Agent

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
RequestKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=100)]

def create_app(db_path=None, ai_transport=None):
    app = FastAPI(title="CampusFlow API",version="1.0.0",docs_url="/api/docs",openapi_url="/api/openapi.json")
    store = Store(db_path or ROOT / "data" / "campusflow.db")
    agent = Agent(store,ai_transport)
    app.state.store = store
    app.state.agent = agent

    @app.exception_handler(ValidationError)
    async def validation_error(request,exc):
        return JSONResponse(status_code=422,content={"detail":"参数校验失败："+str(exc).split("\n")[0]})

    @app.exception_handler(RequestValidationError)
    async def request_validation(request,exc):
        errors = [f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()]
        return JSONResponse(status_code=422,content={"detail":"；".join(errors)})

    @app.get("/api/health")
    def health():
        return {"ok":True,"app":"CampusFlow",**agent.config()}

    @app.get("/api/tasks")
    def tasks(query: str="",course: str="",status: str="",project_id: str=""):
        return store.list(query=query,course=course,status=status,project_id=project_id)

    @app.get("/api/overview")
    def overview():
        return store.overview()

    @app.post("/api/tasks",status_code=201)
    def create_task(task:TaskIn,idempotency_key:RequestKey=None):
        return store.change("create",task.model_dump(mode="json"),idempotency_key)

    @app.patch("/api/tasks/{task_id}")
    def update_task(task_id:int,patch:TaskPatch,idempotency_key:RequestKey=None):
        return store.change("update",patch.model_dump(mode="json",exclude_unset=True),idempotency_key,task_id=task_id)

    @app.delete("/api/tasks/{task_id}")
    def delete_task(task_id:int,idempotency_key:RequestKey=None):
        return store.change("delete",{},idempotency_key,task_id=task_id)

    @app.post("/api/actions/{action_id}/undo")
    def undo_action(action_id:str):
        return store.undo(action_id)

    @app.get("/api/plans")
    def drafts():
        return store.drafts()

    @app.post("/api/plans")
    def create_draft(plan:PlanIn):
        return store.save_draft(plan)

    @app.post("/api/plans/{draft_id}/commit")
    def commit_plan(draft_id:str,plan:PlanIn,idempotency_key:RequestKey=None):
        return store.commit_plan(draft_id,plan,idempotency_key)

    @app.get("/api/chat")
    def history():
        return store.conversation()[1]

    @app.delete("/api/chat")
    async def clear_history():
        async with agent.lock:
            store.clear_chat()
        return {"ok":True}

    @app.post("/api/chat")
    async def chat(request:ChatIn):
        return await agent.chat(request.message,request.request_id)

    @app.post("/api/demo/seed")
    def seed(idempotency_key:RequestKey=None):
        return store.seed(idempotency_key or "sample-data-v1")

    if (ROOT / "dist").exists():
        app.mount("/assets",StaticFiles(directory=ROOT/"dist"/"assets"),name="assets")
        @app.get("/")
        def index():
            return FileResponse(ROOT/"dist"/"index.html")

    return app

app = create_app()
