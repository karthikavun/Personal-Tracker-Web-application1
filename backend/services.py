from collections import Counter
from datetime import date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Attendance, AttendanceStatus, Task, User
from app.schemas import AttendanceCreate, TaskCreate, TaskUpdate, UserCreate, UserLogin, UserUpdate
from app.security import PasswordHasher, TokenManager


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.hasher = PasswordHasher()
        self.tokens = TokenManager()

    def register(self, payload: UserCreate) -> tuple[str, User]:
        self._ensure_unique_email(payload.email)
        user = User(name=payload.name, email=payload.email, hashed_password=self.hasher.hash(payload.password))
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return self.tokens.create_access_token(user.email), user

    def login(self, payload: UserLogin) -> tuple[str, User]:
        user = self.db.query(User).filter(User.email == payload.email).first()
        invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        verified_user = user if user and self.hasher.verify(payload.password, user.hashed_password) else None
        return (self.tokens.create_access_token(verified_user.email), verified_user) if verified_user else (_ for _ in ()).throw(invalid)

    def _ensure_unique_email(self, email: str) -> None:
        exists = self.db.query(User.id).filter(User.email == email).first()
        exists and (_ for _ in ()).throw(HTTPException(status_code=409, detail="Email already registered"))


class ProfileService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def update(self, user: User, payload: UserUpdate) -> User:
        for field, value in payload.model_dump().items():
            setattr(user, field, value)
        self.db.commit()
        self.db.refresh(user)
        return user


class AttendanceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def mark(self, user: User, payload: AttendanceCreate) -> Attendance:
        record = self.db.query(Attendance).filter(Attendance.user_id == user.id, Attendance.date == payload.date).first()
        record = record or Attendance(user_id=user.id, date=payload.date)
        record.status = payload.status
        record.note = payload.note
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def history(self, user: User) -> list[Attendance]:
        return self.db.query(Attendance).filter(Attendance.user_id == user.id).order_by(Attendance.date.desc()).all()


class TaskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, user: User, payload: TaskCreate) -> Task:
        task = Task(user_id=user.id, **payload.model_dump())
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def list(self, user: User) -> list[Task]:
        return self.db.query(Task).filter(Task.user_id == user.id).order_by(Task.created_at.desc()).all()

    def update(self, user: User, task_id: int, payload: TaskUpdate) -> Task:
        task = self._owned_task(user, task_id)
        was_completed = task.completed
        for field, value in payload.model_dump().items():
            setattr(task, field, value)
        task.completed_at = self._completion_time(was_completed, payload.completed, task.completed_at)
        self.db.commit()
        self.db.refresh(task)
        return task

    def delete(self, user: User, task_id: int) -> dict[str, bool]:
        task = self._owned_task(user, task_id)
        self.db.delete(task)
        self.db.commit()
        return {"deleted": True}

    def _owned_task(self, user: User, task_id: int) -> Task:
        task = self.db.query(Task).filter(Task.user_id == user.id, Task.id == task_id).first()
        return task or (_ for _ in ()).throw(HTTPException(status_code=404, detail="Task not found"))

    def _completion_time(self, was_completed: bool, completed: bool, current: datetime | None) -> datetime | None:
        transitions = {
            (False, True): datetime.utcnow(),
            (True, False): None,
        }
        return transitions.get((was_completed, completed), current)


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def build(self, user: User) -> dict:
        tasks = self.db.query(Task).filter(Task.user_id == user.id).all()
        attendance = self.db.query(Attendance).filter(Attendance.user_id == user.id).all()
        completed = sum(task.completed for task in tasks)
        total_tasks = len(tasks)
        present_days = sum(record.status in {AttendanceStatus.present, AttendanceStatus.late, AttendanceStatus.half_day} for record in attendance)
        attendance_rate = self._percentage(present_days, len(attendance))
        completion_rate = self._percentage(completed, total_tasks)
        productivity_score = round((attendance_rate * 0.4) + (completion_rate * 0.6))

        return {
            "cards": [
                {"label": "Attendance", "value": f"{attendance_rate}%", "trend": "daily discipline"},
                {"label": "Tasks Done", "value": f"{completed}/{total_tasks}", "trend": "completion rhythm"},
                {"label": "Productivity", "value": f"{productivity_score}%", "trend": "balanced score"},
                {"label": "Streak", "value": str(self._streak(attendance)), "trend": "active days"},
            ],
            "weekly_progress": self._weekly_progress(user),
            "task_mix": self._task_mix(tasks),
            "recent_tasks": sorted(tasks, key=lambda task: task.created_at, reverse=True)[:5],
            "current_streak": self._streak(attendance),
            "productivity_score": productivity_score,
        }

    def _weekly_progress(self, user: User) -> list[dict]:
        today = date.today()
        days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
        attendance_by_day = {
            item.date: item for item in self.db.query(Attendance).filter(Attendance.user_id == user.id, Attendance.date.in_(days)).all()
        }
        completed_by_day = dict(
            self.db.query(func.date(Task.completed_at), func.count(Task.id))
            .filter(Task.user_id == user.id, Task.completed.is_(True), func.date(Task.completed_at).in_(days))
            .group_by(func.date(Task.completed_at))
            .all()
        )
        return [
            {
                "name": day.strftime("%a"),
                "attendance": int(attendance_by_day.get(day, Attendance(status=AttendanceStatus.absent)).status != AttendanceStatus.absent),
                "completed": int(completed_by_day.get(day, 0)),
                "score": int(attendance_by_day.get(day, Attendance(status=AttendanceStatus.absent)).status != AttendanceStatus.absent) * 40
                + min(int(completed_by_day.get(day, 0)) * 20, 60),
            }
            for day in days
        ]

    def _task_mix(self, tasks: list[Task]) -> list[dict]:
        counts = Counter("completed" if task.completed else "pending" for task in tasks)
        return [
            {"name": "Completed", "completed": counts["completed"], "pending": 0},
            {"name": "Pending", "completed": 0, "pending": counts["pending"]},
        ]

    def _percentage(self, numerator: int, denominator: int) -> int:
        return round((numerator / max(denominator, 1)) * 100)

    def _streak(self, attendance: list[Attendance]) -> int:
        active_dates = {item.date for item in attendance if item.status != AttendanceStatus.absent}
        streak = 0
        cursor = date.today()
        while cursor in active_dates:
            streak += 1
            cursor -= timedelta(days=1)
        return streak
