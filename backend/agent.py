from __future__ import annotations

import asyncio
import json
import os
import time
from uuid import uuid4
import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from .models import TaskIn, TaskPatch, PlanIn, now

def function(name, description, properties, required=None):
    return {"type":"function","function":{"name":name,"description":description,
            "parameters":{"type":"object","properties":properties,"required":required or [],
                          "additionalProperties":False}}}

TASK_SCHEMA = TaskIn.model_json_schema()
TASK_SCHEMA["properties"].pop("project_id", None)
TASK_SCHEMA["properties"].pop("project_title", None)
TASK_SCHEMA["properties"].pop("step_index", None)
PLAN_SCHEMA = PlanIn.model_json_schema()
PLAN_SCHEMA.pop("$defs", None)
PLAN_SCHEMA["properties"]["tasks"]["items"] = TASK_SCHEMA

TOOLS = [
    function("list_tasks", "查询真实任务。修改、完成或删除前先查询取得真实ID；多个同名对象必须澄清。",
             {k:{"type":"string"} for k in ("query","course","status","date_from","date_to")}),
    function("get_overview", "读取真实的完成率、待办数、逾期数和今天待办数。", {}),
    function("create_task", "创建单条待办。时间未知可留空。安排时间必须使用含+08:00时区的ISO日期。",
             {"task":TASK_SCHEMA}, ["task"]),
    function("update_task", "修改已查询的任务。截止日期和安排时间是不同字段。清除日期传null。",
             {"task_id":{"type":"integer"}, "changes":TaskPatch.model_json_schema()}, ["task_id","changes"]),
    function("complete_task", "将明确的任务标记为已完成。", {"task_id":{"type":"integer"}}, ["task_id"]),
    function("delete_task", "删除明确指定的单条任务，可撤销。批量删除需先列清单并征求确认。",
             {"task_id":{"type":"integer"}}, ["task_id"]),
    function("propose_plan", "生成可编辑的计划草稿，不创建正式任务。用户在界面点击保存后才落库。检查每日时间预算。",
             {"plan":PLAN_SCHEMA}, ["plan"]),
]

class Agent:
    def __init__(self, store, transport=None):
        self.store = store
        self.transport = transport
        self.lock = asyncio.Lock()

    def config(self):
        return {"configured":bool(os.getenv("DEEPSEEK_API_KEY","").strip()),
                "model":os.getenv("AI_MODEL","deepseek-flash"),
                "provider":"DeepSeek", "timezone":"Asia/Shanghai"}

    def execute(self, name, args, request_id):
        if name == "list_tasks":
            allowed = {"query","course","status","date_from","date_to"}
            if set(args) - allowed or any(not isinstance(v, str) for v in args.values()):
                raise ValueError("查询参数必须是受支持的文本字段")
            return {"tasks":self.store.list(**args)}
        if name == "get_overview":
            return self.store.overview()
        if name == "create_task":
            task = TaskIn(**args["task"])
            return self.store.change("create",task.model_dump(mode="json"),request_id)
        if name == "update_task":
            patch = TaskPatch(**args["changes"]).model_dump(mode="json",exclude_unset=True)
            return self.store.change("update",patch,request_id,task_id=int(args["task_id"]))
        if name == "complete_task":
            return self.store.change("update",{"status":"done"},request_id,task_id=int(args["task_id"]))
        if name == "delete_task":
            return self.store.change("delete",{},request_id,task_id=int(args["task_id"]))
        if name == "propose_plan":
            return {"draft":self.store.save_draft(PlanIn(**args["plan"]))}
        raise ValueError("未知工具")

    async def chat(self, text, request_id):
        async with self.lock:
            cached = self.store.chat_receipt(request_id,text)
            if cached:
                return cached
            if not self.config()["configured"]:
                raise HTTPException(503,"尚未配置 API Key。请在项目根目录 .env 中设置 DEEPSEEK_API_KEY 并重启后端。")
            turns, ui = self.store.conversation()
            system = f"""你是课伴 CampusFlow 的校园学习任务助手，使用简体中文。
当前北京时间：{now().isoformat()}，星期{now().isoweekday()}。本周从周一开始，下周指下一自然周。
你的职责：管理本地学习任务、拆解目标、安排时间。任务信息必须通过工具查询，不能编造任务、ID或统计。
把截止日期due_date和安排时间scheduled_start分开；单改一项不能擅自改另一项。所有安排时间带+08:00。
缺少任务截止日期可以创建无日期待办；缺少排期时段应追问。'晚上'未给时刻时可建议19:00并明确展示为建议。
对'第二步'等指代先查询相关项目，根据step_index确定步骤；无法唯一定位则提问。先查后改。
需要多步计划时使用propose_plan生成草稿，绝不把草稿当作已保存；让用户在卡片上编辑并保存。
计划从当前时间之后开始；各步骤在目标截止日前完成，遵守每日时间预算及已查到的安排；无法满足时说明冲突。
批量删除先列清单请用户确认。只操作用户明确要求的对象。工具失败不能声称成功。
完成、创建、修改后根据真实工具结果简洁回复。规划建议不保证全局最优。"""
            messages = [{"role":"system","content":system}]
            for turn in turns[-6:]:
                messages.extend(turn)
            current = [{"role":"user","content":text}]
            messages.extend(current)
            traces, tokens = [], {"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
            content, error = "", None
            try:
                timeout = min(max(float(os.getenv("AI_TIMEOUT_SECONDS","45")),5),90)
                async with httpx.AsyncClient(timeout=timeout,transport=self.transport,trust_env=False) as client:
                    for _ in range(4):
                        response = await client.post(
                            os.getenv("AI_BASE_URL","https://api.deepseek.com").rstrip("/")+"/chat/completions",
                            headers={"Authorization":"Bearer "+os.environ["DEEPSEEK_API_KEY"]},
                            json={"model":self.config()["model"],"messages":messages,"tools":TOOLS,
                                  "thinking":{"type":"disabled"},"temperature":0.3,"max_tokens":2500})
                        if response.status_code != 200:
                            hints = {401:"API Key 无效，请检查后端配置",402:"API 余额不足",
                                     429:"API 请求过于频繁或额度受限",503:"模型服务暂时不可用"}
                            raise RuntimeError(hints.get(response.status_code,f"模型服务返回 HTTP {response.status_code}"))
                        body = response.json()
                        usage = body.get("usage") or {}
                        for key in tokens:
                            tokens[key] += int(usage.get(key) or 0)
                        raw = body["choices"][0]["message"]
                        msg = {"role":"assistant","content":raw.get("content") or ""}
                        calls = raw.get("tool_calls") or []
                        if calls:
                            msg["tool_calls"] = calls
                        messages.append(msg)
                        current.append(msg)
                        if not calls:
                            content = msg["content"] or "模型未返回内容，请换一种表述。"
                            break
                        for call in calls:
                            started = time.perf_counter()
                            name = call.get("function",{}).get("name","unknown")
                            args = {}
                            try:
                                if len(traces) >= 10:
                                    raise ValueError("本轮工具调用数量已达上限，请分步操作")
                                args = json.loads(call["function"].get("arguments","{}"))
                                if not isinstance(args,dict):
                                    raise ValueError("工具参数必须是对象")
                                result = self.execute(name,args,f"chat:{request_id}:{call['id']}")
                                state = "success"
                            except (ValidationError,ValueError,KeyError,TypeError,HTTPException) as exc:
                                detail = exc.detail if isinstance(exc,HTTPException) else str(exc)
                                result, state = {"error":detail}, "error"
                            traces.append({"id":call["id"],"name":name,"arguments":args,"result":result,
                                           "status":state,"duration_ms":round((time.perf_counter()-started)*1000)})
                            tool_message = {"role":"tool","tool_call_id":call["id"],
                                            "content":json.dumps(result,ensure_ascii=False)}
                            messages.append(tool_message)
                            current.append(tool_message)
                    else:
                        content = "已达到本轮操作上限。请查看执行记录，或继续发送下一条指令。"
            except httpx.TimeoutException:
                error = "模型响应超时，请稍后重试。"
            except (httpx.HTTPError,RuntimeError,ValueError,KeyError,IndexError,TypeError) as exc:
                error = str(exc) if isinstance(exc,RuntimeError) else "无法获取有效模型回复，请检查 API 配置或网络。"
            if error:
                wrote = any(t["status"]=="success" and t["result"].get("action_id") for t in traces)
                content = error + (" 已成功执行的操作保留在任务列表中，可通过下方记录撤销。" if wrote else " 本次未收到完整回复。")
            if not current or current[-1].get("role") != "assistant" or current[-1].get("tool_calls"):
                current.append({"role":"assistant","content":content})
            else:
                current[-1]["content"] = content
            answer = {"id":str(uuid4()),"role":"assistant","content":content,"traces":traces,
                      "usage":tokens,"error":bool(error),"created_at":now().isoformat()}
            ui.extend([{"id":str(uuid4()),"role":"user","content":text,"created_at":now().isoformat()},answer])
            turns.append(current)
            self.store.save_conversation(turns,ui,request_id,text,answer)
            return answer
