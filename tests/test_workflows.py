import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.db")) as client:
        yield client


def test_no_key_disables_only_chat(client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert client.get("/api/health").json()["configured"] is False
    assert client.post("/api/chat", json={"message": "查看待办", "request_id": "no-key-001"}).status_code == 503
    assert client.post("/api/tasks", json={"title": "完成实验"}).status_code == 201


def test_task_changes_persist_and_undo(tmp_path):
    path = tmp_path / "tasks.db"
    with TestClient(create_app(path)) as client:
        task = client.post("/api/tasks", json={
            "title": "复习线性回归", "due_date": "2030-06-08",
            "scheduled_start": "2030-06-06T19:00:00+08:00",
        }).json()["tasks"][0]
        url = f"/api/tasks/{task['id']}"
        updated = client.patch(url, json={"due_date": "2030-06-09"}).json()["tasks"][0]
        assert updated["scheduled_start"] == task["scheduled_start"]
        assert client.patch(url, json={"status": "done"}).status_code == 200
        assert client.get("/api/overview").json()["completed"] == 1
        deleted = client.delete(url).json()
        assert client.get("/api/tasks").json() == []
        assert client.post(f"/api/actions/{deleted['action_id']}/undo").status_code == 200
    with TestClient(create_app(path)) as reopened:
        restored = reopened.get("/api/tasks").json()[0]
        assert (restored["id"], restored["due_date"], restored["status"]) == (task["id"], "2030-06-09", "done")


def test_retries_do_not_duplicate_writes(client):
    headers = {"Idempotency-Key": "task-001"}
    first = client.post("/api/tasks", json={"title": "复习"}, headers=headers)
    retry = client.post("/api/tasks", json={"title": "复习"}, headers=headers)
    assert first.json() == retry.json()
    assert client.post("/api/tasks", json={"title": "换一个标题"}, headers=headers).status_code == 409
    assert len(client.get("/api/tasks").json()) == 1


def test_plan_conflict_rolls_back_tasks_and_draft(client):
    assert client.post("/api/tasks", json={
        "title": "已有课程", "scheduled_start": "2030-06-06T15:00:00+08:00",
    }).status_code == 201
    draft_input = {"title": "课程报告", "tasks": [{"title": "调研"}, {"title": "撰写"}]}
    draft = client.post("/api/plans", json=draft_input).json()
    commit_url = f"/api/plans/{draft['id']}/commit"
    changed = {"title": "修改后的报告", "tasks": [
        {"title": "调研", "scheduled_start": "2030-06-06T13:00:00+08:00"},
        {"title": "撰写", "scheduled_start": "2030-06-06T15:15:00+08:00"},
    ]}
    assert client.post(commit_url, json=changed).status_code == 409
    assert len(client.get("/api/tasks").json()) == 1
    saved_draft = client.get("/api/plans").json()[0]
    assert (saved_draft["title"], saved_draft["status"]) == ("课程报告", "pending")

    changed["tasks"][1]["scheduled_start"] = "2030-06-06T16:00:00+08:00"
    key = {"Idempotency-Key": "save-plan-01"}
    response = client.post(commit_url, json=changed, headers=key)
    assert response.status_code == 200
    saved = response.json()
    assert [task["step_index"] for task in saved["tasks"]] == [1, 2]
    assert len({task["project_id"] for task in saved["tasks"]}) == 1
    assert client.post(commit_url, json=changed, headers=key).json() == saved
    assert client.post(f"/api/actions/{saved['action_id']}/undo").status_code == 200
    assert len(client.get("/api/tasks").json()) == 1
    assert client.get("/api/plans").json()[0]["status"] == "pending"


def test_plan_budget_and_timezone_validation(client):
    payload = {"title": "复习计划", "daily_budget_minutes": 60, "tasks": [
        {"title": "复习一", "scheduled_start": "2030-06-06T23:30:00+08:00", "duration_minutes": 60},
        {"title": "复习二", "scheduled_start": "2030-06-07T12:00:00+08:00", "duration_minutes": 45},
    ]}
    assert client.post("/api/plans", json=payload).status_code == 422
    assert client.post("/api/tasks", json={
        "title": "没有时区", "scheduled_start": "2030-06-06T19:00:00",
    }).status_code == 422


def test_agent_calls_provider_executes_tool_and_reuses_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "mock-test-key")
    monkeypatch.setenv("AI_BASE_URL", "https://api.deepseek.com")
    requests = []

    def model(request):
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert request.headers["authorization"] == "Bearer mock-test-key"
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "create-01", "type": "function", "function": {
                    "name": "create_task", "arguments": json.dumps({"task": {"title": "查阅人工智能文献"}}),
                },
            }]}
        else:
            tool_result = body["messages"][-1]
            assert tool_result["role"] == "tool"
            assert tool_result["tool_call_id"] == "create-01"
            assert json.loads(tool_result["content"])["tasks"][0]["title"] == "查阅人工智能文献"
            message = {"role": "assistant", "content": "已创建文献查阅任务。"}
        return httpx.Response(200, json={"choices": [{"message": message}], "usage": {"total_tokens": 50}})

    with TestClient(create_app(tmp_path / "agent.db", httpx.MockTransport(model))) as client:
        payload = {"message": "加一项查阅人工智能文献", "request_id": "agent-create-01"}
        answer = client.post("/api/chat", json=payload).json()
        assert answer["traces"][0]["status"] == "success"
        assert answer["usage"]["total_tokens"] == 100
        assert len(client.get("/api/tasks").json()) == 1
        assert client.post("/api/chat", json=payload).json() == answer
        assert len(requests) == 2


def test_provider_auth_failure_is_visible(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "invalid-test-key")
    transport = httpx.MockTransport(lambda _: httpx.Response(401))
    with TestClient(create_app(tmp_path / "failure.db", transport)) as client:
        answer = client.post("/api/chat", json={"message": "添加任务", "request_id": "invalid-key-01"}).json()
        assert answer["error"] is True
        assert "API Key 无效" in answer["content"]
        assert client.get("/api/tasks").json() == []
