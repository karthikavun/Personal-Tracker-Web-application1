from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import AttendanceStatus, TaskCategory, TaskPriority


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    goal: str = Field(max_length=255)
    skills: str = Field(max_length=255)
    daily_target: str = Field(max_length=255)
    motivational_quote: str = Field(max_length=255)
    profile_photo: str | None = None


class UserPublic(BaseModel):
    id: int
    name: str
    email: EmailStr
    goal: str
    skills: str
    daily_target: str
    motivational_quote: str
    profile_photo: str | None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class AttendanceCreate(BaseModel):
    date: date
    status: AttendanceStatus
    note: str = Field(default="", max_length=255)


class AttendancePublic(BaseModel):
    id: int
    date: date
    status: AttendanceStatus
    check_in_time: datetime
    note: str

    model_config = ConfigDict(from_attributes=True)


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    description: str = ""
    priority: TaskPriority = TaskPriority.medium
    category: TaskCategory = TaskCategory.personal
    deadline: datetime | None = None


class TaskUpdate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    description: str = ""
    priority: TaskPriority = TaskPriority.medium
    category: TaskCategory = TaskCategory.personal
    deadline: datetime | None = None
    completed: bool = False


class TaskPublic(BaseModel):
    id: int
    title: str
    description: str
    priority: TaskPriority
    category: TaskCategory
    completed: bool
    deadline: datetime | None
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class StatCard(BaseModel):
    label: str
    value: str
    trend: str


class ChartPoint(BaseModel):
    name: str
    attendance: int = 0
    completed: int = 0
    pending: int = 0
    score: int = 0


class DashboardResponse(BaseModel):
    cards: list[StatCard]
    weekly_progress: list[ChartPoint]
    task_mix: list[ChartPoint]
    recent_tasks: list[TaskPublic]
    current_streak: int
    productivity_score: int
