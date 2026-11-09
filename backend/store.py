from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from .models import TaskIn, CST, now

def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS tasks(
                id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1, deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS actions(
                id TEXT PRIMARY KEY, kind TEXT, before_json TEXT, after_json TEXT,
                draft_id TEXT, undone INTEGER DEFAULT 0, created_at TEXT);
            CREATE TABLE IF NOT EXISTS receipts(
                id TEXT PRIMARY KEY, digest TEXT, response TEXT);
            CREATE TABLE IF NOT EXISTS drafts(
                id TEXT PRIMARY KEY, payload TEXT, status TEXT DEFAULT 'pending', created_at TEXT);
            CREATE TABLE IF NOT EXISTS conversation(
                id INTEGER PRIMARY KEY CHECK(id=1), turns TEXT NOT NULL, messages TEXT NOT NULL);
            INSERT OR IGNORE INTO conversation VALUES(1, '[]', '[]');
            CREATE TABLE IF NOT EXISTS chat_receipts(
                id TEXT PRIMARY KEY, message TEXT NOT NULL, response TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def public(row):
        return {**json.loads(row["payload"]), "id": row["id"], "version": row["version"],
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def list(self, **filters):
        with self.connect() as db:
            tasks = [self.public(r) for r in db.execute("SELECT * FROM tasks WHERE deleted=0 ORDER BY id DESC")]
        for key in ("status", "course", "project_id"):
            if filters.get(key):
                tasks = [t for t in tasks if t[key] == filters[key]]
        query = (filters.get("query") or "").strip().lower()
        if query:
            tasks = [t for t in tasks if query in " ".join(
                t.get(key) or "" for key in ("title", "course", "description", "project_title")
            ).lower()]
        if filters.get("date_from") or filters.get("date_to"):
            first = date.fromisoformat(filters["date_from"]) if filters.get("date_from") else date.min
            last = date.fromisoformat(filters["date_to"]) if filters.get("date_to") else date.max
            if first > last:
                raise ValueError("查询结束日期不能早于开始日期")
            tasks = [
                task for task in tasks if any(
                    first <= date.fromisoformat(value[:10]) <= last
                    for value in (task["scheduled_start"], task["due_date"]) if value
                )
            ]
        return tasks

    def overview(self):
        tasks = self.list()
        today = now().date().isoformat()
        done = [t for t in tasks if t["status"] == "done"]
        active = [t for t in tasks if t["status"] != "done"]
        return {
            "total": len(tasks), "completed": len(done), "pending": len(active),
            "overdue": sum(bool(t["due_date"] and t["due_date"] < today) for t in active),
            "today": sum(bool((t["scheduled_start"] and t["scheduled_start"][:10] == today)
                              or t["due_date"] == today) for t in active),
            "completion_rate": round(len(done) / len(tasks) * 100) if tasks else 0,
            "today_date": today,
        }

    def conflict_check(self, db, task, excluding=None):
        if not task.get("scheduled_start") or task["status"] == "done":
            return
        start = datetime.fromisoformat(task["scheduled_start"])
        end = start + timedelta(minutes=task["duration_minutes"])
        for row in db.execute("SELECT * FROM tasks WHERE deleted=0"):
            if row["id"] == excluding:
                continue
            other = json.loads(row["payload"])
            if not other["scheduled_start"] or other["status"] == "done":
                continue
            other_start = datetime.fromisoformat(other["scheduled_start"])
            other_end = other_start + timedelta(minutes=other["duration_minutes"])
            if start < other_end and other_start < end:
                raise HTTPException(409, f"与「{other['title']}」的安排重叠，请调整时间")

    def change(self, kind, payload, request_id, task_id=None, draft_id=None):
        digest = hashlib.sha256(encode([kind, payload, task_id, draft_id]).encode()).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if request_id:
                receipt = db.execute("SELECT * FROM receipts WHERE id=?", (request_id,)).fetchone()
                if receipt:
                    if receipt["digest"] != digest:
                        raise HTTPException(409, "请求标识已用于另一项操作")
                    return json.loads(receipt["response"])
            before, after, result = {}, {}, []
            if kind == "plan":
                draft = db.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
                if not draft or draft["status"] != "pending":
                    raise HTTPException(409, "此计划已保存或不存在")
            if kind == "seed" and db.execute("SELECT 1 FROM tasks WHERE deleted=0 LIMIT 1").fetchone():
                raise HTTPException(409, "已有任务。示例数据只能在空工作区导入")
            if kind in ("create", "plan", "seed"):
                entries = payload["tasks"] if kind == "plan" else (payload if kind == "seed" else [payload])
                group = str(uuid4()) if kind == "plan" else None
                for index, value in enumerate(entries, start=1):
                    value = dict(value)
                    if kind == "plan":
                        value.update(project_id=group, project_title=payload["title"], step_index=index)
                    value = TaskIn(**value).model_dump(mode="json")
                    self.conflict_check(db, value)
                    stamp = now().isoformat()
                    cursor = db.execute("INSERT INTO tasks(payload, created_at, updated_at) VALUES(?,?,?)",
                                        (encode(value), stamp, stamp))
                    tid = cursor.lastrowid
                    before[str(tid)] = None
                    row = dict(db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())
                    after[str(tid)] = row
                    result.append(self.public(row))
                if kind == "plan":
                    db.execute("UPDATE drafts SET status='committed', payload=? WHERE id=?",
                               (encode(payload), draft_id))
            else:
                row = db.execute("SELECT * FROM tasks WHERE id=? AND deleted=0", (task_id,)).fetchone()
                if not row:
                    raise HTTPException(404, "任务不存在或已删除")
                before[str(task_id)] = dict(row)
                value = json.loads(row["payload"])
                if kind == "delete":
                    db.execute("UPDATE tasks SET deleted=1, version=version+1, updated_at=? WHERE id=?",
                               (now().isoformat(), task_id))
                else:
                    value = TaskIn(**{**value, **payload}).model_dump(mode="json")
                    self.conflict_check(db, value, task_id)
                    db.execute("UPDATE tasks SET payload=?, version=version+1, updated_at=? WHERE id=?",
                               (encode(value), now().isoformat(), task_id))
                new = dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
                after[str(task_id)] = new
                if not new["deleted"]:
                    result.append(self.public(new))
            action_id = str(uuid4())
            db.execute("INSERT INTO actions(id,kind,before_json,after_json,draft_id,created_at) VALUES(?,?,?,?,?,?)",
                       (action_id, kind, encode(before), encode(after), draft_id, now().isoformat()))
            response = {"action_id": action_id, "tasks": result, "ok": True}
            if request_id:
                db.execute("INSERT INTO receipts VALUES(?,?,?)", (request_id, digest, encode(response)))
            return response

    def undo(self, action_id):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            action = db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
            if not action or action["undone"]:
                raise HTTPException(409, "此操作不可撤销或已经撤销")
            before, after = json.loads(action["before_json"]), json.loads(action["after_json"])
            for tid, expected in after.items():
                row = db.execute("SELECT * FROM tasks WHERE id=?", (int(tid),)).fetchone()
                if not row or dict(row) != expected:
                    raise HTTPException(409, "相关任务已有后续修改，请先撤销后续操作")
            # Check restored schedules against unaffected tasks and each other before restoring.
            excluded_ids = [int(tid) for tid in before]
            if excluded_ids:
                placeholders = ",".join("?" for _ in excluded_ids)
                db.execute(f"UPDATE tasks SET deleted=1 WHERE id IN ({placeholders})", excluded_ids)
            for tid, previous in before.items():
                if previous is None:
                    db.execute("DELETE FROM tasks WHERE id=?", (int(tid),))
                else:
                    if not previous["deleted"]:
                        self.conflict_check(db, json.loads(previous["payload"]), int(tid))
                    db.execute("UPDATE tasks SET payload=?,version=?,deleted=?,created_at=?,updated_at=? WHERE id=?",
                               (previous["payload"], previous["version"], previous["deleted"],
                                previous["created_at"], previous["updated_at"], int(tid)))
            db.execute("UPDATE actions SET undone=1 WHERE id=?", (action_id,))
            if action["draft_id"]:
                db.execute("UPDATE drafts SET status='pending' WHERE id=?", (action["draft_id"],))
            return {"ok": True}

    def save_draft(self, plan):
        draft_id = str(uuid4())
        value = plan.model_dump(mode="json")
        with self.connect() as db:
            db.execute("INSERT INTO drafts(id,payload,created_at) VALUES(?,?,?)",
                       (draft_id, encode(value), now().isoformat()))
        return {"id": draft_id, "status": "pending", **value}

    def drafts(self):
        with self.connect() as db:
            return [{"id": row["id"], "status": row["status"], **json.loads(row["payload"])}
                    for row in db.execute("SELECT * FROM drafts ORDER BY created_at DESC LIMIT 20")]

    def commit_plan(self, draft_id, plan, request_id):
        return self.change("plan", plan.model_dump(mode="json"), request_id, draft_id=draft_id)

    def conversation(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM conversation WHERE id=1").fetchone()
            return json.loads(row["turns"]), json.loads(row["messages"])

    def save_conversation(self, turns, messages, request_id, message, response):
        with self.connect() as db:
            db.execute("UPDATE conversation SET turns=?, messages=? WHERE id=1",
                       (encode(turns[-12:]), encode(messages[-80:])))
            db.execute("INSERT INTO chat_receipts VALUES(?,?,?)", (request_id, message, encode(response)))

    def chat_receipt(self, request_id, message):
        with self.connect() as db:
            row = db.execute("SELECT * FROM chat_receipts WHERE id=?", (request_id,)).fetchone()
            if not row:
                return None
            if row["message"] != message:
                raise HTTPException(409, "聊天请求标识已被使用")
            return json.loads(row["response"])

    def clear_chat(self):
        with self.connect() as db:
            db.execute("UPDATE conversation SET turns='[]',messages='[]' WHERE id=1")
            db.execute("DELETE FROM chat_receipts")

    def seed(self, request_id):
        today = now().date()
        specs = [
            ("完成人工智能课程报告", "人工智能", 2, "high", "doing", 14, 90, "course-report", "人工智能课程报告"),
            ("整理文献与研究问题", "人工智能", 0, "medium", "done", 9, 45, "course-report", "人工智能课程报告"),
            ("复习线性回归与梯度下降", "机器学习", 0, "high", "todo", 19, 60, None, None),
            ("完成数据库实验三", "数据库原理", 1, "medium", "todo", 15, 60, None, None),
            ("准备小组汇报提纲", "人工智能", 3, "medium", "todo", 10, 45, "course-report", "人工智能课程报告"),
            ("阅读英文论文并做笔记", "学术英语", 4, "low", "todo", 16, 45, None, None),
            ("提交算法作业", "数据结构", -1, "high", "todo", None, 45, None, None),
        ]
        tasks = []
        for title, course, offset, priority, status, hour, duration, group, group_title in specs:
            day = today + timedelta(days=offset)
            task = TaskIn(title=title, course=course, due_date=day,
                          scheduled_start=datetime(day.year,day.month,day.day,hour,0,tzinfo=CST) if hour else None,
                          priority=priority,status=status,duration_minutes=duration,
                          project_id=group,project_title=group_title)
            tasks.append(task.model_dump(mode="json"))
        return self.change("seed", tasks, request_id)
