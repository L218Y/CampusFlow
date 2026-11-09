from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator

CST = timezone(timedelta(hours=8))
def now():
    return datetime.now(CST)

class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    course: str = Field(default="个人学习", max_length=60)
    description: str = Field(default="", max_length=2000)
    priority: Literal["low", "medium", "high"] = "medium"
    status: Literal["todo", "doing", "done"] = "todo"
    due_date: date | None = None
    scheduled_start: datetime | None = None
    duration_minutes: int = Field(default=45, ge=5, le=480)
    project_id: str | None = Field(default=None, max_length=80)
    project_title: str | None = Field(default=None, max_length=160)
    step_index: int | None = Field(default=None, ge=1, le=20)

    @field_validator("title", "course")
    @classmethod
    def strip_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("标题和课程不能为空")
        return value

    @field_validator("scheduled_start")
    @classmethod
    def timezone_required(cls, value):
        if value and value.tzinfo is None:
            raise ValueError("安排时间必须包含时区")
        return value.astimezone(CST) if value else value

    @model_validator(mode="after")
    def deadline_check(self):
        if self.scheduled_start and self.due_date:
            end = self.scheduled_start + timedelta(minutes=self.duration_minutes)
            cutoff = datetime.combine(self.due_date + timedelta(days=1), datetime.min.time(), tzinfo=CST)
            if end > cutoff:
                raise ValueError("安排时间超出截止日期")
        return self

class TaskPatch(BaseModel):
    title: str | None = None
    course: str | None = None
    description: str | None = None
    priority: Literal["low", "medium", "high"] | None = None
    status: Literal["todo", "doing", "done"] | None = None
    due_date: date | None = None
    scheduled_start: datetime | None = None
    duration_minutes: int | None = None

class PlanIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    goal: str = Field(default="", max_length=1000)
    daily_budget_minutes: int = Field(default=120, ge=5, le=480)
    tasks: list[TaskIn] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def budget_check(self):
        totals = {}
        for task in self.tasks:
            start = task.scheduled_start
            if not start:
                continue
            end = start + timedelta(minutes=task.duration_minutes)
            while start < end:
                midnight = datetime.combine(start.date() + timedelta(days=1), datetime.min.time(), tzinfo=CST)
                until = min(midnight, end)
                day = start.date()
                totals[day] = totals.get(day, 0) + (until - start).total_seconds() / 60
                start = until
        if any(total > self.daily_budget_minutes for total in totals.values()):
            raise ValueError("计划超过每日时间预算，请调整时长或日期")
        return self

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=3000)
    request_id: str = Field(min_length=8, max_length=100)
