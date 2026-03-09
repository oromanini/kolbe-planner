from fastapi import (
    FastAPI,
    APIRouter,
    HTTPException,
    Cookie,
    Response,
    Header,
    Query,
    UploadFile,
    File,
    Form,
)
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re
import asyncio
import base64
import smtplib
from email.message import EmailMessage
from zoneinfo import ZoneInfo
from io import BytesIO
import importlib


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# MongoDB connection
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# ============ MODELS ============


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    onboarding_completed: bool = False
    settings: dict = Field(default_factory=lambda: {"kolbe_mode_enabled": False})
    created_at: datetime


class Quote(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    mode: Literal["neutral", "kolbe"]
    text: str
    author: str
    tags: List[str] = Field(default_factory=list)
    active: bool = True
    created_at: datetime
    updated_at: datetime


class UserSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_token: str
    user_id: str
    expires_at: datetime
    created_at: datetime


class Habit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    habit_id: str
    user_id: str
    name: str
    color: str
    icon: str
    start_date: str  # YYYY-MM-DD format
    end_date: str  # YYYY-MM-DD format
    frequency: Literal["daily", "weekdays", "custom"] = "daily"
    selected_weekdays: List[int] = Field(default_factory=list)
    order: int
    created_at: datetime


class HabitCompletion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    completion_id: str
    habit_id: str
    user_id: str
    date: str  # YYYY-MM-DD format
    completed: bool
    completed_at: Optional[datetime] = None


# ============ INPUT MODELS ============


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class HabitCreate(BaseModel):
    name: str
    color: str
    icon: str = "circle"
    start_date: str
    end_date: str
    frequency: Literal["daily", "weekdays", "custom"] = "daily"
    selected_weekdays: List[int] = Field(default_factory=list)


class HabitUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    frequency: Optional[Literal["daily", "weekdays", "custom"]] = None
    selected_weekdays: Optional[List[int]] = None
    order: Optional[int] = None


class CompletionToggle(BaseModel):
    habit_id: str
    date: str  # YYYY-MM-DD


class UserSettingsUpdate(BaseModel):
    kolbe_mode_enabled: bool


class QuoteCreate(BaseModel):
    mode: Literal["neutral", "kolbe"]
    text: str
    author: str
    tags: List[str] = Field(default_factory=list)
    active: bool = True


class QuoteImportPayload(BaseModel):
    version: int
    items: List[QuoteCreate]


class QuoteBulkDeletePayload(BaseModel):
    ids: List[str]


class NotificationItem(BaseModel):
    id: str
    dedupe_key: str
    type: Literal["deadline", "late", "month_review"]
    source: Literal["goals", "finance"] = "goals"
    tone: Literal["info", "warning", "danger"] = "info"
    message: str
    created_at: str


# ============ AUTH HELPER ============


async def get_current_user(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> User:
    """Get current user from session token (cookie or header)"""
    token = session_token

    # Fallback to Authorization header
    if not token and authorization:
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        else:
            token = authorization

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Find session
    session_doc = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})

    if not session_doc:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Check expiry
    expires_at = session_doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    # Get user
    user_doc = await db.users.find_one({"user_id": session_doc["user_id"]}, {"_id": 0})

    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")

    # Parse datetime
    if isinstance(user_doc.get("created_at"), str):
        user_doc["created_at"] = datetime.fromisoformat(user_doc["created_at"])
    user_doc["settings"] = normalize_user_settings(user_doc.get("settings"))

    return User(**user_doc)


def normalize_user_settings(settings: Optional[dict]) -> dict:
    normalized = {"kolbe_mode_enabled": False}
    if isinstance(settings, dict):
        normalized["kolbe_mode_enabled"] = bool(
            settings.get("kolbe_mode_enabled", False)
        )
    return normalized


def normalize_quote_key(mode: str, text: str, author: str) -> str:
    def clean(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip().lower())

    return f"{clean(mode)}::{clean(text)}::{clean(author)}"


def sanitize_mongo_document(document: dict) -> dict:
    cleaned = dict(document)
    cleaned.pop("_id", None)
    return cleaned


def get_user_timezone(user_doc: dict) -> str:
    settings = user_doc.get("settings") or {}
    tz = settings.get("timezone")
    return tz if isinstance(tz, str) and tz else "America/Sao_Paulo"


def get_local_day_key(tz_name: str) -> str:
    try:
        return datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def parse_day_key(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid date format. Use YYYY-MM-DD"
        ) from exc


def ensure_period_is_valid(
    start_date: str, end_date: str, min_date: Optional[str] = None
):
    start = parse_day_key(start_date)
    end = parse_day_key(end_date)
    if end < start:
        raise HTTPException(
            status_code=400,
            detail="End date must be greater than or equal to start date",
        )
    if min_date:
        minimum = parse_day_key(min_date)
        if start < minimum:
            raise HTTPException(
                status_code=400, detail="Start date cannot be in the past"
            )


def is_habit_scheduled_for_date(habit: dict, selected_date: datetime) -> bool:
    frequency = habit.get("frequency") or "daily"
    if frequency == "weekdays":
        return selected_date.weekday() < 5
    if frequency == "custom":
        selected_weekdays = habit.get("selected_weekdays") or []
        return selected_date.weekday() in selected_weekdays
    return True


def sanitize_selected_weekdays(selected_weekdays: Optional[List[int]]) -> List[int]:
    if not selected_weekdays:
        return []

    normalized_days = sorted(set(selected_weekdays))
    if any(day < 0 or day > 4 for day in normalized_days):
        raise HTTPException(
            status_code=400,
            detail="selected_weekdays must contain values between 0 (Seg) and 4 (Sex)",
        )
    return normalized_days


def validate_frequency_selection(frequency: str, selected_weekdays: List[int]):
    if frequency == "custom" and not selected_weekdays:
        raise HTTPException(
            status_code=400, detail="Select at least one weekday for custom frequency"
        )


def compose_goal_notifications(
    habits: List[dict], completions: List[dict], now_local: datetime
) -> List[dict]:
    notifications: List[dict] = []
    today_key = now_local.strftime("%Y-%m-%d")
    today = datetime.strptime(today_key, "%Y-%m-%d")

    for habit in habits:
        habit_id = habit.get("habit_id")
        name = (habit.get("name") or "seu objetivo").strip()
        start_key = habit.get("start_date")
        end_key = habit.get("end_date")

        if not start_key or not end_key:
            continue

        try:
            start_date = parse_day_key(start_key)
            end_date = parse_day_key(end_key)
        except HTTPException:
            continue

        days_remaining = (end_date - today).days
        if 1 <= days_remaining <= 3 and today >= start_date:
            message = f"Faltam {days_remaining} dias para concluir o objetivo {name}."
            notifications.append(
                {
                    "id": f"goal-deadline-{habit_id}-{today_key}",
                    "dedupe_key": f"goal_deadline:{habit_id}:{days_remaining}:{today_key}",
                    "type": "deadline",
                    "source": "goals",
                    "tone": "warning",
                    "message": message,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        if (
            now_local.hour >= 23
            and today_key >= start_key
            and today_key <= end_key
            and is_habit_scheduled_for_date(habit, today)
        ):
            completion_for_today = next(
                (
                    comp
                    for comp in completions
                    if comp.get("habit_id") == habit_id
                    and comp.get("date") == today_key
                ),
                None,
            )
            if not (completion_for_today and completion_for_today.get("completed")):
                message = (
                    f"Já são 23h e você ainda não concluiu o objetivo {name} hoje."
                )
                notifications.append(
                    {
                        "id": f"goal-late-{habit_id}-{today_key}",
                        "dedupe_key": f"goal_late:{habit_id}:{today_key}",
                        "type": "late",
                        "source": "goals",
                        "tone": "danger",
                        "message": message,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

    if now_local.day == 1:
        notifications.append(
            {
                "id": f"month-review-goals-{today_key}",
                "dedupe_key": f"month_review:goals:{today_key}",
                "type": "month_review",
                "source": "goals",
                "tone": "info",
                "message": "Hoje é dia 1: revise e ajuste suas metas do mês para manter o foco.",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        notifications.append(
            {
                "id": f"month-review-finance-{today_key}",
                "dedupe_key": f"month_review:finance:{today_key}",
                "type": "month_review",
                "source": "finance",
                "tone": "info",
                "message": "Começo do mês: revise seu planejamento financeiro e atualize orçamento e categorias.",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    return notifications


async def persist_notifications(user_id: str, items: List[dict]) -> List[dict]:
    if not items:
        return []

    new_items: List[dict] = []
    for item in items:
        record = {
            **item,
            "user_id": user_id,
        }
        existing = await db.notifications.find_one(
            {"user_id": user_id, "dedupe_key": item["dedupe_key"]}, {"_id": 0, "id": 1}
        )
        if existing:
            continue

        await db.notifications.insert_one(record)
        new_items.append(sanitize_mongo_document(record))

    return new_items


def _build_notification_email_html(user_name: str, items: List[dict]) -> str:
    rows = "".join([f"<li>{item['message']}</li>" for item in items])
    return f"""
    <html>
      <body>
        <p>Olá, {user_name}!</p>
        <p>Você recebeu novos alertas no Kolbe Planner:</p>
        <ul>{rows}</ul>
        <p>Abra o planner para acompanhar e ajustar suas metas.</p>
      </body>
    </html>
    """


async def dispatch_email_notifications(user: User, items: List[dict]) -> bool:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    sender = os.environ.get("SMTP_FROM_EMAIL")
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")

    if not host or not sender or not username or not password:
        logger.info(
            "SMTP not configured; skipping email notifications for user %s",
            user.user_id,
        )
        return False

    message = EmailMessage()
    message["Subject"] = "Notificações do Kolbe Planner"
    message["From"] = sender
    message["To"] = user.email
    plain_text = "\n".join([f"- {item['message']}" for item in items])
    message.set_content(
        f"Olá, {user.name}!\n\nVocê recebeu novos alertas:\n{plain_text}"
    )
    message.add_alternative(
        _build_notification_email_html(user.name, items), subtype="html"
    )

    try:
        with smtplib.SMTP(host=host, port=port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)
    except Exception as exc:
        logger.exception(
            "Failed to send notification email for user %s: %s", user.user_id, exc
        )
        return False

    return True


async def require_admin_user(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> User:
    user = await get_current_user(session_token, authorization)
    admin_emails = [
        email.strip().lower()
        for email in os.environ.get(
            "ADMIN_EMAILS", "oscar.romanini.jr@gmail.com"
        ).split(",")
        if email.strip()
    ]
    is_admin = user.email.lower() in admin_emails
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ============ AUTH ENDPOINTS ============


@api_router.post("/auth/register")
async def register(request: RegisterRequest, response: Response):
    """Register new user with email/password"""

    # Check if user exists
    existing = await db.users.find_one({"email": request.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash password
    password_hash = hashlib.sha256(request.password.encode()).hexdigest()

    # Create user
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    await db.users.insert_one(
        {
            "user_id": user_id,
            "email": request.email,
            "name": request.name,
            "password_hash": password_hash,
            "picture": None,
            "onboarding_completed": False,
            "settings": {"kolbe_mode_enabled": False},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Create session
    session_token = f"jwt_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    await db.user_sessions.insert_one(
        {
            "session_token": session_token,
            "user_id": user_id,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60,
    )

    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if isinstance(user_doc.get("created_at"), str):
        user_doc["created_at"] = datetime.fromisoformat(user_doc["created_at"])
    user_doc["settings"] = normalize_user_settings(user_doc.get("settings"))

    return {**User(**user_doc).model_dump(), "session_token": session_token}


@api_router.post("/auth/login")
async def login(request: LoginRequest, response: Response):
    """Login with email/password"""

    # Find user
    user_doc = await db.users.find_one({"email": request.email}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Verify password
    password_hash = hashlib.sha256(request.password.encode()).hexdigest()
    if user_doc.get("password_hash") != password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create session
    session_token = f"jwt_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    await db.user_sessions.insert_one(
        {
            "session_token": session_token,
            "user_id": user_doc["user_id"],
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60,
    )

    if isinstance(user_doc.get("created_at"), str):
        user_doc["created_at"] = datetime.fromisoformat(user_doc["created_at"])
    user_doc["settings"] = normalize_user_settings(user_doc.get("settings"))

    return {**User(**user_doc).model_dump(), "session_token": session_token}


@api_router.get("/auth/me")
async def get_me(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    """Get current user info"""
    user = await get_current_user(session_token, authorization)
    return user


@api_router.post("/auth/logout")
async def logout(response: Response, user: User = None):
    """Logout user"""
    try:
        user = await get_current_user()
        # Delete session
        await db.user_sessions.delete_many({"user_id": user.user_id})
    except:
        pass

    # Clear cookie
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out"}


@api_router.post("/auth/complete-onboarding")
async def complete_onboarding(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    """Mark onboarding as completed"""
    user = await get_current_user(session_token, authorization)

    await db.users.update_one(
        {"user_id": user.user_id}, {"$set": {"onboarding_completed": True}}
    )

    return {"message": "Onboarding completed"}


@api_router.put("/users/settings")
async def update_user_settings(
    payload: UserSettingsUpdate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)

    current_settings = normalize_user_settings(user.settings)
    new_settings = {
        **current_settings,
        "kolbe_mode_enabled": payload.kolbe_mode_enabled,
    }

    await db.users.update_one(
        {"user_id": user.user_id}, {"$set": {"settings": new_settings}}
    )

    return {"settings": new_settings}


@api_router.get("/quotes/daily")
async def get_daily_quote(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    mode = "kolbe" if user.settings.get("kolbe_mode_enabled") else "neutral"
    user_doc = (
        await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "settings": 1})
        or {}
    )
    timezone_name = get_user_timezone(user_doc)
    local_day = get_local_day_key(timezone_name)

    stored = await db.user_daily_quotes.find_one(
        {"user_id": user.user_id, "local_day": local_day, "mode": mode}, {"_id": 0}
    )
    if stored:
        quote = await db.quotes.find_one(
            {"id": stored["quote_id"], "active": True}, {"_id": 0}
        )
        if quote:
            return {"quote": quote, "mode": mode, "local_day": local_day}

    quotes = await db.quotes.find({"mode": mode, "active": True}, {"_id": 0}).to_list(
        2000
    )
    selected_mode = mode
    if not quotes and mode == "kolbe":
        quotes = await db.quotes.find(
            {"mode": "neutral", "active": True}, {"_id": 0}
        ).to_list(2000)
        selected_mode = "neutral"

    if not quotes:
        return {"quote": None, "mode": selected_mode, "local_day": local_day}

    seed_key = f"{user.user_id}:{local_day}:{selected_mode}".encode()
    seed = int(hashlib.sha256(seed_key).hexdigest(), 16)
    quote = quotes[seed % len(quotes)]

    await db.user_daily_quotes.update_one(
        {"user_id": user.user_id, "local_day": local_day, "mode": selected_mode},
        {
            "$set": {
                "quote_id": quote["id"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()},
        },
        upsert=True,
    )

    return {"quote": quote, "mode": selected_mode, "local_day": local_day}


# ============ HABITS ENDPOINTS ============


@api_router.get("/habits", response_model=List[Habit])
async def get_habits(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    """Get user's habits"""
    user = await get_current_user(session_token, authorization)

    habits = (
        await db.habits.find({"user_id": user.user_id}, {"_id": 0})
        .sort("order", 1)
        .to_list(100)
    )

    # Parse datetimes
    for habit in habits:
        if isinstance(habit.get("created_at"), str):
            habit["created_at"] = datetime.fromisoformat(habit["created_at"])
        start_date = habit.get("start_date")
        if not start_date:
            start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            habit["start_date"] = start_date
        if not habit.get("end_date"):
            habit["end_date"] = start_date
        if not habit.get("frequency"):
            habit["frequency"] = "daily"
        habit["selected_weekdays"] = sanitize_selected_weekdays(
            habit.get("selected_weekdays")
        )

    return habits


@api_router.post("/habits", response_model=Habit, status_code=201)
async def create_habit(
    habit_data: HabitCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    """Create a new habit (max 10)"""
    user = await get_current_user(session_token, authorization)

    # Check limit
    count = await db.habits.count_documents({"user_id": user.user_id})
    if count >= 10:
        raise HTTPException(status_code=400, detail="Maximum 10 habits allowed")

    # Get next order
    last_habit = await db.habits.find_one(
        {"user_id": user.user_id}, {"_id": 0, "order": 1}, sort=[("order", -1)]
    )
    next_order = (last_habit["order"] + 1) if last_habit else 0

    user_doc = await db.users.find_one(
        {"user_id": user.user_id}, {"_id": 0, "settings": 1}
    )
    today_key = get_local_day_key(get_user_timezone(user_doc or {}))
    ensure_period_is_valid(habit_data.start_date, habit_data.end_date, today_key)
    selected_weekdays = sanitize_selected_weekdays(habit_data.selected_weekdays)
    validate_frequency_selection(habit_data.frequency, selected_weekdays)

    habit = Habit(
        habit_id=f"habit_{uuid.uuid4().hex[:12]}",
        user_id=user.user_id,
        name=habit_data.name,
        color=habit_data.color,
        icon=habit_data.icon,
        start_date=habit_data.start_date,
        end_date=habit_data.end_date,
        frequency=habit_data.frequency,
        selected_weekdays=selected_weekdays,
        order=next_order,
        created_at=datetime.now(timezone.utc),
    )

    doc = habit.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.habits.insert_one(doc)

    return habit


@api_router.put("/habits/{habit_id}", response_model=Habit)
async def update_habit(
    habit_id: str,
    habit_data: HabitUpdate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    """Update a habit"""
    user = await get_current_user(session_token, authorization)

    # Check ownership
    habit = await db.habits.find_one(
        {"habit_id": habit_id, "user_id": user.user_id}, {"_id": 0}
    )
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    # Update
    update_data = {k: v for k, v in habit_data.model_dump().items() if v is not None}
    if update_data:
        user_doc = await db.users.find_one(
            {"user_id": user.user_id}, {"_id": 0, "settings": 1}
        )
        today_key = get_local_day_key(get_user_timezone(user_doc or {}))
        next_start_date = update_data.get(
            "start_date", habit.get("start_date", today_key)
        )
        next_end_date = update_data.get(
            "end_date", habit.get("end_date", next_start_date)
        )
        ensure_period_is_valid(next_start_date, next_end_date, today_key)

        next_frequency = update_data.get("frequency", habit.get("frequency", "daily"))
        next_selected_weekdays = sanitize_selected_weekdays(
            update_data.get("selected_weekdays", habit.get("selected_weekdays"))
        )
        validate_frequency_selection(next_frequency, next_selected_weekdays)
        update_data["selected_weekdays"] = next_selected_weekdays

        await db.habits.update_one({"habit_id": habit_id}, {"$set": update_data})

    # Return updated
    updated_habit = await db.habits.find_one({"habit_id": habit_id}, {"_id": 0})
    if isinstance(updated_habit.get("created_at"), str):
        updated_habit["created_at"] = datetime.fromisoformat(
            updated_habit["created_at"]
        )
    if not updated_habit.get("start_date"):
        updated_habit["start_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not updated_habit.get("end_date"):
        updated_habit["end_date"] = updated_habit["start_date"]
    if not updated_habit.get("frequency"):
        updated_habit["frequency"] = "daily"
    updated_habit["selected_weekdays"] = sanitize_selected_weekdays(
        updated_habit.get("selected_weekdays")
    )

    return Habit(**updated_habit)


@api_router.delete("/habits/{habit_id}")
async def delete_habit(
    habit_id: str,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    """Delete a habit and its completions"""
    user = await get_current_user(session_token, authorization)

    result = await db.habits.delete_one({"habit_id": habit_id, "user_id": user.user_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Habit not found")

    # Delete completions
    await db.habit_completions.delete_many({"habit_id": habit_id})

    return {"message": "Habit deleted"}


@api_router.post("/habits/initialize-defaults")
async def initialize_default_habits(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    """Create default example habits"""
    user = await get_current_user(session_token, authorization)

    # Check if user already has habits
    count = await db.habits.count_documents({"user_id": user.user_id})
    if count > 0:
        raise HTTPException(status_code=400, detail="User already has habits")

    default_habits = [
        {"name": "Exercício", "color": "#CD1C33", "icon": "activity"},
        {"name": "Leitura", "color": "#0F1B2D", "icon": "book-open"},
        {"name": "Meditação", "color": "#8A8F98", "icon": "brain"},
        {"name": "Estudar", "color": "#D4AF37", "icon": "graduation-cap"},
        {"name": "Duolingo", "color": "#58CC02", "icon": "globe"},
    ]


# ============ FINANCIAL MODELS ============


class FinancialMethod(BaseModel):
    model_config = ConfigDict(extra="ignore")
    method_id: str
    user_id: str
    name: str
    created_at: datetime


class FinancialCategory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    category_id: str
    user_id: str
    name: str
    type: Literal["expense", "income"] = "expense"
    created_at: datetime


class Expense(BaseModel):
    model_config = ConfigDict(extra="ignore")
    expense_id: str
    user_id: str
    name: str
    amount: float
    method_id: str
    category: str
    subcategory: Optional[str] = None
    month: str  # YYYY-MM
    created_at: datetime


class Income(BaseModel):
    model_config = ConfigDict(extra="ignore")
    income_id: str
    user_id: str
    name: str
    amount: float
    category: Optional[str] = None
    month: str  # YYYY-MM
    created_at: datetime


class Savings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    savings_id: str
    user_id: str
    name: str
    type: str  # caixinha, investimento, reserva
    amount: float
    created_at: datetime
    updated_at: datetime


class InvoiceReaderJob(BaseModel):
    model_config = ConfigDict(extra="ignore")
    job_id: str
    user_id: str
    status: Literal["queued", "processing", "completed", "failed"] = "queued"
    source_type: Literal["credit_card_pdf"] = "credit_card_pdf"
    filename: str
    requested_month: str
    bank_name: Optional[str] = None
    card_suffix: Optional[str] = None
    category_name: Optional[str] = None
    expected_total: Optional[float] = None
    parsed_total: Optional[float] = None
    parsed_count: int = 0
    created_expense_ids: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# Input models
class ExpenseCreate(BaseModel):
    name: str
    amount: float
    method_id: str
    category: str
    subcategory: Optional[str] = None
    month: str


class ExpenseUpdate(BaseModel):
    name: str
    amount: float
    method_id: str
    category: str
    subcategory: Optional[str] = None
    month: str


class IncomeCreate(BaseModel):
    name: str
    amount: float
    category: str
    month: str


class SavingsCreate(BaseModel):
    name: str
    type: str
    amount: float


class MethodCreate(BaseModel):
    name: str


DEFAULT_FINANCIAL_METHODS = [
    "pix",
    "dinheiro",
    "crédito a vista",
    "crédito parcelado",
    "debito",
    "boleto",
    "promissoria",
    "crediario",
    "wallet",
    "outro",
]


def normalize_method_name(name: str) -> str:
    return name.strip().casefold()


def normalize_category_name(name: str) -> str:
    return name.strip()


def normalize_category_key(name: str) -> str:
    return normalize_category_name(name).casefold()


async def ensure_default_financial_methods(user_id: str):
    existing_methods = await db.financial_methods.find(
        {"user_id": user_id}, {"_id": 0, "name": 1}
    ).to_list(200)
    existing_names = {
        normalize_method_name(method.get("name", "")) for method in existing_methods
    }

    for name in DEFAULT_FINANCIAL_METHODS:
        if normalize_method_name(name) in existing_names:
            continue

        await db.financial_methods.insert_one(
            {
                "method_id": f"method_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "name": name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )


async def ensure_financial_category_indexes() -> None:
    """Remove stale unique indexes that block multiple categories per user."""
    indexes = await db.financial_categories.index_information()
    for index_name, index_meta in indexes.items():
        if index_name == "_id_":
            continue

        keys = [tuple(entry) for entry in index_meta.get("key", [])]
        if index_meta.get("unique") and keys in (
            [("user_id", 1)],
            [("user_id", 1), ("name_key", 1)],
        ):
            await db.financial_categories.drop_index(index_name)

    await db.financial_categories.update_many(
        {"type": {"$exists": False}}, {"$set": {"type": "expense"}}
    )


class CategoryCreate(BaseModel):
    name: str
    type: Literal["expense", "income"] = "expense"


class CategoryUpdate(BaseModel):
    name: str
    type: Literal["expense", "income"] = "expense"


async def resolve_user_category_name(
    user_id: str, raw_category: str, expected_type: Optional[str] = None
) -> Optional[str]:
    """Resolve category payload to the canonical category name stored for the user."""
    category_value = (raw_category or "").strip()
    if not category_value:
        return None

    base_query = {"user_id": user_id}
    if expected_type:
        base_query["type"] = expected_type

    by_id = await db.financial_categories.find_one(
        {**base_query, "category_id": category_value},
        {"_id": 0, "name": 1},
    )
    if by_id and by_id.get("name"):
        return by_id["name"]

    normalized_key = normalize_category_key(category_value)
    by_key = await db.financial_categories.find_one(
        {**base_query, "name_key": normalized_key},
        {"_id": 0, "name": 1},
    )
    if by_key and by_key.get("name"):
        return by_key["name"]

    by_exact_name = await db.financial_categories.find_one(
        {**base_query, "name": category_value},
        {"_id": 0, "name": 1},
    )
    if by_exact_name and by_exact_name.get("name"):
        return by_exact_name["name"]

    return None


class InvoiceImportRequest(BaseModel):
    requested_month: str


INVOICE_JOB_RETENTION_MINUTES = 5


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


async def cleanup_expired_invoice_jobs(user_id: str):
    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=INVOICE_JOB_RETENTION_MINUTES
    )
    jobs = await db.invoice_reader_jobs.find(
        {"user_id": user_id}, {"_id": 0, "job_id": 1, "status": 1, "finished_at": 1}
    ).to_list(500)
    for job in jobs:
        if job.get("status") not in {"completed", "failed"}:
            continue
        finished_at = parse_iso_datetime(job.get("finished_at"))
        if not finished_at:
            continue
        if finished_at.tzinfo is None:
            finished_at = finished_at.replace(tzinfo=timezone.utc)
        if finished_at <= cutoff:
            await db.invoice_reader_jobs.delete_one(
                {"job_id": job.get("job_id"), "user_id": user_id}
            )


def detect_bank_name(raw_text: str) -> str:
    text = (raw_text or "").lower()
    if "nubank" in text or " nu " in text:
        return "Nubank"
    if "itaú" in text or "itau" in text:
        return "Itau"
    if "neon" in text:
        return "Neon"
    return "Cartão"


def detect_card_suffix(raw_text: str) -> str:
    text = raw_text or ""
    patterns = [
        r"final\s*(\d{4})",
        r"\*{2,}\s*(\d{4})",
        r"\.{2,}\s*(\d{4})",
        r"cart[aã]o\s*(\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return "XXXX"


def parse_brl_number(raw_value: str) -> Optional[float]:
    candidate = (raw_value or "").strip()
    if not candidate:
        return None
    normalized = re.sub(r"[^0-9,.-]", "", candidate)
    if not normalized:
        return None
    normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


INVOICE_NON_PURCHASE_FLAGS = [
    "pagamento",
    "estorno",
    "anuidade",
    "juros",
    "iof",
    "encargos",
    "seguro",
    "limite",
    "saldo restante",
    "fatura anterior",
    "pagamento mínimo",
    "composição do pagamento mínimo",
    "parcelamentos",
    "juros rotativo",
    "total a pagar",
    "valor da entrada",
    "valor da parcela",
    "juros totais",
    "cet",
]


def clean_invoice_item_name(name: str) -> str:
    cleaned = (name or "").replace("→", " ").replace("•", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -\n\t")
    return cleaned


def is_invoice_purchase_name(name: str) -> bool:
    cleaned = clean_invoice_item_name(name)
    lowered = cleaned.casefold()
    if not cleaned:
        return False
    return not any(flag in lowered for flag in INVOICE_NON_PURCHASE_FLAGS)


def extract_invoice_items_with_ai(
    raw_text: str, expected_total: Optional[float] = None
) -> List[dict]:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return []

    snippet = (raw_text or "")[:24000]
    expected_hint = ""
    if expected_total is not None:
        expected_hint = (
            f"Total esperado da fatura: {expected_total:.2f}. "
            "Priorize linhas de compra cuja soma bata com esse total.\n"
        )

    prompt = (
        "Extraia apenas lançamentos de compra de uma fatura de cartão. "
        "Ignore pagamentos, estornos, IOF, juros, encargos, anuidade, seguros e limites. "
        "Ignore também seções de parcelamento/rotativo como: saldo restante, CET, valor da entrada, valor da parcela, total a pagar e composição de pagamento mínimo. "
        "Considere layouts de bancos brasileiros variados (Itau, Nubank, Bradesco, Santander e outros). "
        "Responda somente JSON válido no formato: "
        '{"items":[{"name":"texto","amount":123.45}]}. '
        "Use amount com ponto decimal e valor positivo.\n"
        f"{expected_hint}\n"
        f"Texto bruto:\n{snippet}"
    )

    payload = {
        "model": os.getenv("OPENAI_INVOICE_MODEL", "gpt-4.1-mini"),
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Você é um extrator de lançamentos de fatura. Retorne apenas JSON.",
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    }
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "invoice_items",
                "schema": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "amount": {"type": "number"},
                                },
                                "required": ["name", "amount"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["items"],
                    "additionalProperties": False,
                },
            }
        },
    }

    return run_invoice_ai_payload(payload, api_key)


def extract_invoice_items_from_pdf_with_ai(
    pdf_bytes: bytes, filename: str, expected_total: Optional[float] = None
) -> List[dict]:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key or not pdf_bytes:
        return []

    encoded_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    expected_hint = ""
    if expected_total is not None:
        expected_hint = (
            f"Total esperado da fatura: {expected_total:.2f}. "
            "Priorize linhas de compra cuja soma bata com esse total.\n"
        )

    prompt = (
        "Extraia apenas lançamentos de compra da fatura anexada. "
        "Ignore pagamentos, estornos, IOF, juros, encargos, anuidade, seguros e limites. "
        "Ignore também seções de parcelamento/rotativo como: saldo restante, CET, valor da entrada, valor da parcela, total a pagar e composição de pagamento mínimo. "
        "Em faturas do Nubank, foque na seção TRANSAÇÕES e descarte as seções de Pagamentos e Financiamentos. "
        "Responda somente JSON válido no formato: "
        '{"items":[{"name":"texto","amount":123.45}]}. '
        "Use amount com ponto decimal e valor positivo.\n"
        f"{expected_hint}"
    )

    payload = {
        "model": os.getenv("OPENAI_INVOICE_MODEL", "gpt-4.1-mini"),
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Você é um extrator de lançamentos de fatura. Retorne apenas JSON.",
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": filename or "fatura.pdf",
                        "file_data": f"data:application/pdf;base64,{encoded_pdf}",
                    },
                    {
                        "type": "input_text",
                        "text": prompt,
                    },
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "invoice_items",
                "schema": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "amount": {"type": "number"},
                                },
                                "required": ["name", "amount"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["items"],
                    "additionalProperties": False,
                },
            }
        },
    }

    return run_invoice_ai_payload(payload, api_key)


def run_invoice_ai_payload(payload: dict, api_key: str) -> List[dict]:

    try:
        import requests

        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=40,
        )
        response.raise_for_status()
        body = response.json()
    except Exception:
        return []

    output_text = body.get("output_text")
    if not output_text:
        for item in body.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    output_text = content["text"]
                    break
            if output_text:
                break

    if not output_text:
        return []

    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError:
        return []

    cleaned = []
    seen = set()
    for entry in parsed.get("items", []):
        name = clean_invoice_item_name(str(entry.get("name", "")))
        amount_raw = entry.get("amount")
        amount = (
            float(amount_raw)
            if isinstance(amount_raw, (int, float))
            else parse_brl_number(str(amount_raw))
        )
        if not name or amount is None or amount <= 0 or not is_invoice_purchase_name(name):
            continue
        key = (name.casefold(), round(amount, 2))
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({"name": name, "amount": round(amount, 2)})
    return cleaned


def extract_expected_total(raw_text: str) -> Optional[float]:
    patterns = [
        r"total\s+da\s+sua\s+fatura[^0-9-]{0,50}(-?[0-9][0-9\.,]*)",
        r"total\s+da\s+fatura[^0-9-]{0,50}(-?[0-9][0-9\.,]*)",
        r"lan[çc]amentos\s+no\s+cart[aã]o[^0-9-]{0,50}(-?[0-9][0-9\.,]*)",
        r"total\s+dos\s+lan[çc]amentos\s+atuais[^0-9-]{0,50}(-?[0-9][0-9\.,]*)",
        r"valor\s+do\s+documento[^0-9-]{0,50}(-?[0-9][0-9\.,]*)",
        r"valor\s+total(?!\s+financiado)[^0-9-]{0,50}(-?[0-9][0-9\.,]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if not match:
            continue
        amount = parse_brl_number(match.group(1))
        if amount is not None and amount > 0:
            return amount
    return None


def select_items_matching_expected_total(
    items: List[dict], expected_total: Optional[float]
) -> Optional[List[dict]]:
    if expected_total is None or not items:
        return None

    target_cents = int(round(expected_total * 100))
    item_cents = [int(round(max(item.get("amount", 0), 0) * 100)) for item in items]
    parsed_cents = sum(item_cents)
    if parsed_cents == target_cents:
        return items
    if target_cents <= 0 or parsed_cents < target_cents:
        return None

    # Subset-sum in cents to recover when AI mixes "lançamentos atuais" with
    # "próximas faturas" sections.
    reachable = {0: None}
    for idx, cents in enumerate(item_cents):
        if cents <= 0:
            continue
        for total in sorted(reachable.keys(), reverse=True):
            new_total = total + cents
            if new_total > target_cents or new_total in reachable:
                continue
            reachable[new_total] = (total, idx)
        if target_cents in reachable:
            break

    if target_cents not in reachable:
        return None

    selected_indices = set()
    cursor = target_cents
    while cursor:
        previous = reachable.get(cursor)
        if previous is None:
            return None
        cursor, idx = previous
        selected_indices.add(idx)

    if len(selected_indices) == len(items):
        return items
    return [item for idx, item in enumerate(items) if idx in selected_indices]


def _parse_invoice_entries(raw_text: str, *, keep_purchase_entries: bool) -> List[dict]:
    entries = []
    seen = set()
    lines = [
        line.strip() for line in (raw_text or "").splitlines() if line and line.strip()
    ]
    patterns = [
        re.compile(
            r"^\d{2}\s+[A-ZÇÃÕÁÉÍÓÚ]{3}\s+(.+?)\s+(?:R\$\s*)?([0-9\.,]+)$",
            re.IGNORECASE,
        ),
        re.compile(r"^\d{2}/\d{2}\s+(.+?)\s+([0-9\.,]+)$", re.IGNORECASE),
        re.compile(r"^(.+?)\s+-\s+([0-9]+/[0-9]+)\s*-\s+([0-9\.,]+)$", re.IGNORECASE),
    ]

    for line in lines:
        for pattern in patterns:
            match = pattern.match(line)
            if not match:
                continue
            if pattern.pattern.startswith(r"^\d{2}\s+"):
                description = clean_invoice_item_name(match.group(1).strip())
                amount_raw = match.group(2)
            elif pattern.pattern.startswith(r"^\d{2}/"):
                description = clean_invoice_item_name(match.group(1).strip())
                amount_raw = match.group(2)
            else:
                description = clean_invoice_item_name(
                    f"{match.group(1).strip()} - {match.group(2).strip()}"
                )
                amount_raw = match.group(3)
            is_purchase = is_invoice_purchase_name(description)
            if keep_purchase_entries != is_purchase:
                continue
            amount = parse_brl_number(amount_raw)
            if amount is None or amount <= 0:
                continue
            key = (description.casefold(), round(amount, 2))
            if key in seen:
                continue
            seen.add(key)
            entries.append({"name": description, "amount": round(amount, 2)})
            break

    compact_pattern = re.compile(
        r"(\d{2}\s+[A-ZÇÃÕÁÉÍÓÚ]{3})\s+(.+?)\s+(?:R\$\s*)?([0-9\.,]+)(?=\s+\d{2}\s+[A-ZÇÃÕÁÉÍÓÚ]{3}\s+|$)",
        re.IGNORECASE,
    )
    compact_text = re.sub(r"\s+", " ", raw_text or "").strip()
    for match in compact_pattern.finditer(compact_text):
        description = clean_invoice_item_name(match.group(2).strip())
        is_purchase = is_invoice_purchase_name(description)
        if keep_purchase_entries != is_purchase:
            continue
        amount = parse_brl_number(match.group(3))
        if amount is None or amount <= 0:
            continue
        key = (description.casefold(), round(amount, 2))
        if key in seen:
            continue
        seen.add(key)
        entries.append({"name": description, "amount": round(amount, 2)})

    return entries


def extract_invoice_items(raw_text: str) -> List[dict]:
    return _parse_invoice_entries(raw_text, keep_purchase_entries=True)


def extract_non_purchase_invoice_items(raw_text: str) -> List[dict]:
    return _parse_invoice_entries(raw_text, keep_purchase_entries=False)


def extract_pdf_text(pdf_bytes: bytes) -> str:
    extracted_pages: List[str] = []
    pypdf_spec = importlib.util.find_spec("pypdf")
    if pypdf_spec is not None:
        pypdf_module = importlib.import_module("pypdf")
        reader = pypdf_module.PdfReader(BytesIO(pdf_bytes or b""))
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            if text:
                extracted_pages.append(text)

    if extracted_pages:
        return "\n".join(extracted_pages)

    # Fallback lightweight extraction for text-based PDFs.
    decoded = (pdf_bytes or b"").decode("latin-1", errors="ignore")
    decoded = decoded.replace("\r", "\n")
    decoded = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", decoded)
    return decoded


async def ensure_expense_category(user_id: str, category_name: str) -> str:
    normalized_name = normalize_category_name(category_name)
    normalized_key = normalize_category_key(normalized_name)
    existing = await db.financial_categories.find_one(
        {"user_id": user_id, "type": "expense", "name_key": normalized_key},
        {"_id": 0},
    )
    if existing:
        return existing["name"]

    category_doc = {
        "category_id": f"cat_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "name": normalized_name,
        "name_key": normalized_key,
        "type": "expense",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.financial_categories.insert_one(category_doc)
    return category_doc["name"]


async def _set_invoice_job(job_id: str, patch: dict):
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.invoice_reader_jobs.update_one({"job_id": job_id}, {"$set": patch})


async def process_invoice_reader_job(
    job_id: str, user_id: str, requested_month: str, filename: str, pdf_bytes: bytes
):
    await _set_invoice_job(
        job_id,
        {"status": "processing", "started_at": datetime.now(timezone.utc).isoformat()},
    )
    errors = []
    created_ids = []
    try:
        raw_text = await asyncio.to_thread(extract_pdf_text, pdf_bytes)
        bank = detect_bank_name(raw_text)
        suffix = detect_card_suffix(raw_text)
        category_name = await ensure_expense_category(user_id, f"{bank} final {suffix}")

        await _set_invoice_job(
            job_id,
            {"bank_name": bank, "card_suffix": suffix, "category_name": category_name},
        )

        methods = await db.financial_methods.find(
            {"user_id": user_id}, {"_id": 0}
        ).to_list(100)
        method = next(
            (
                m
                for m in methods
                if normalize_method_name(m.get("name", "")) == "crédito a vista"
            ),
            None,
        )
        if not method:
            await ensure_default_financial_methods(user_id)
            methods = await db.financial_methods.find(
                {"user_id": user_id}, {"_id": 0}
            ).to_list(100)
            method = next(
                (
                    m
                    for m in methods
                    if normalize_method_name(m.get("name", "")) == "crédito a vista"
                ),
                None,
            )
        if not method:
            raise ValueError("Método padrão de cartão não encontrado")

        expected_total = extract_expected_total(raw_text)
        items = await asyncio.to_thread(
            extract_invoice_items_from_pdf_with_ai, pdf_bytes, filename, expected_total
        )
        if not items:
            items = await asyncio.to_thread(
                extract_invoice_items_with_ai, raw_text, expected_total
            )
        if not items:
            items = await asyncio.to_thread(extract_invoice_items, raw_text)
        matched_items = select_items_matching_expected_total(items, expected_total)
        if matched_items:
            items = matched_items
        parsed_total = round(sum(item["amount"] for item in items), 2)

        await _set_invoice_job(
            job_id,
            {
                "parsed_count": len(items),
                "parsed_total": parsed_total,
                "expected_total": expected_total,
            },
        )

        if not items:
            raise ValueError(
                "A IA não conseguiu identificar lançamentos da fatura. Adicione os gastos manualmente."
            )

        if expected_total is not None and abs(parsed_total - expected_total) > 0.01:
            non_purchase_items = extract_non_purchase_invoice_items(raw_text)
            non_purchase_total = round(
                sum(item["amount"] for item in non_purchase_items), 2
            )
            gap = round(expected_total - parsed_total, 2)
            if (
                gap > 0
                and non_purchase_total > 0
                and abs(non_purchase_total - gap) <= 0.01
            ):
                await _set_invoice_job(
                    job_id,
                    {
                        "non_purchase_count": len(non_purchase_items),
                        "non_purchase_total": non_purchase_total,
                    },
                )
            else:
                raise ValueError(
                    f"A IA não conseguiu conciliar a soma dos lançamentos ({parsed_total:.2f}) com o total da fatura ({expected_total:.2f}). Adicione os gastos manualmente."
                )

        now_iso = datetime.now(timezone.utc).isoformat()
        for item in items:
            expense_doc = {
                "expense_id": f"exp_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "name": item["name"],
                "amount": item["amount"],
                "method_id": method["method_id"],
                "category": category_name,
                "subcategory": "fatura-cartao",
                "month": requested_month,
                "created_at": now_iso,
            }
            await db.expenses.insert_one(expense_doc)
            created_ids.append(expense_doc["expense_id"])

        await _set_invoice_job(
            job_id,
            {
                "status": "completed",
                "created_expense_ids": created_ids,
                "errors": [],
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        errors.append(str(exc))
        await _set_invoice_job(
            job_id,
            {
                "status": "failed",
                "errors": errors,
                "created_expense_ids": created_ids,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )


# ============ FINANCIAL ENDPOINTS ============


# Methods
@api_router.get("/finance/methods")
async def get_methods(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    await ensure_default_financial_methods(user.user_id)
    methods = await db.financial_methods.find(
        {"user_id": user.user_id}, {"_id": 0}
    ).to_list(100)
    return methods


@api_router.post("/finance/methods", status_code=201)
async def create_method(
    data: MethodCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)

    existing_methods = await db.financial_methods.find(
        {"user_id": user.user_id}, {"_id": 0, "name": 1}
    ).to_list(200)
    method_exists = any(
        normalize_method_name(method.get("name", ""))
        == normalize_method_name(data.name)
        for method in existing_methods
    )
    if method_exists:
        raise HTTPException(status_code=409, detail="Method already exists")

    method = {
        "method_id": f"method_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "name": data.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.financial_methods.insert_one(method)
    return sanitize_mongo_document(method)


# Categories
@api_router.get("/finance/categories")
async def get_categories(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    categories = await db.financial_categories.find(
        {"user_id": user.user_id}, {"_id": 0}
    ).to_list(1000)
    return categories


@api_router.post("/finance/categories", status_code=201)
async def create_category(
    data: CategoryCreate,
    response: Response = None,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    normalized_name = normalize_category_name(data.name)
    normalized_key = normalize_category_key(data.name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Category name is required")

    existing_categories = await db.financial_categories.find(
        {"user_id": user.user_id}, {"_id": 0}
    ).to_list(1000)
    existing = next(
        (
            category
            for category in existing_categories
            if category.get("type", "expense") == data.type
            and normalize_category_key(category.get("name", "")) == normalized_key
        ),
        None,
    )
    if existing:
        if response is not None:
            response.status_code = 200
        return existing

    category = {
        "category_id": f"cat_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "name": normalized_name,
        "name_key": normalized_key,
        "type": data.type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.financial_categories.insert_one(category)
    except DuplicateKeyError:
        duplicate = await db.financial_categories.find_one(
            {"user_id": user.user_id, "name_key": normalized_key, "type": data.type},
            {"_id": 0},
        )
        if duplicate:
            if response is not None:
                response.status_code = 200
            return duplicate
        logger.exception(
            "Duplicate key while creating category %s for user %s",
            normalized_name,
            user.user_id,
        )
        raise HTTPException(status_code=409, detail="Category already exists")
    return sanitize_mongo_document(category)


@api_router.put("/finance/categories/{category_id}")
async def update_category(
    category_id: str,
    data: CategoryUpdate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    normalized_name = normalize_category_name(data.name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Category name is required")

    existing = await db.financial_categories.find_one(
        {"category_id": category_id, "user_id": user.user_id}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Category not found")

    normalized_key = normalize_category_key(data.name)
    existing_type = existing.get("type", "expense")
    if (
        normalize_category_key(existing.get("name", "")) != normalized_key
        or existing_type != data.type
    ):
        existing_categories = await db.financial_categories.find(
            {"user_id": user.user_id},
            {"_id": 0, "category_id": 1, "name": 1, "type": 1},
        ).to_list(1000)
        duplicate = next(
            (
                category
                for category in existing_categories
                if category.get("category_id") != category_id
                and category.get("type", "expense") == data.type
                and normalize_category_key(category.get("name", "")) == normalized_key
            ),
            None,
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Category already exists")

    try:
        await db.financial_categories.update_one(
            {"category_id": category_id, "user_id": user.user_id},
            {
                "$set": {
                    "name": normalized_name,
                    "name_key": normalized_key,
                    "type": data.type,
                }
            },
        )
    except DuplicateKeyError:
        duplicate = await db.financial_categories.find_one(
            {
                "user_id": user.user_id,
                "name_key": normalized_key,
                "type": data.type,
                "category_id": {"$ne": category_id},
            },
            {"_id": 0, "category_id": 1},
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Category already exists")
        logger.exception(
            "Duplicate key while updating category %s for user %s",
            category_id,
            user.user_id,
        )
        raise HTTPException(status_code=500, detail="Error while saving category")

    if existing.get("name") != normalized_name:
        if existing_type == "income":
            await db.incomes.update_many(
                {"user_id": user.user_id, "category": existing.get("name")},
                {"$set": {"category": normalized_name}},
            )
        else:
            await db.expenses.update_many(
                {"user_id": user.user_id, "category": existing.get("name")},
                {"$set": {"category": normalized_name}},
            )

    category = await db.financial_categories.find_one(
        {"category_id": category_id, "user_id": user.user_id}, {"_id": 0}
    )
    return category


@api_router.delete("/finance/categories/{category_id}")
async def delete_category(
    category_id: str,
    force: bool = False,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    category = await db.financial_categories.find_one(
        {"category_id": category_id, "user_id": user.user_id}, {"_id": 0}
    )
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    category_type = category.get("type", "expense")
    collection = db.incomes if category_type == "income" else db.expenses

    linked_items_count = await collection.count_documents(
        {"user_id": user.user_id, "category": category["name"]}
    )

    if linked_items_count > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Category has linked items",
                "linked_items_count": linked_items_count,
            },
        )

    await db.financial_categories.delete_one(
        {"category_id": category_id, "user_id": user.user_id}
    )
    if linked_items_count > 0:
        await collection.delete_many(
            {"user_id": user.user_id, "category": category["name"]}
        )

    return {"message": "Category deleted", "deleted_items": linked_items_count}


# Expenses
@api_router.get("/finance/expenses")
async def get_expenses(
    month: str,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    expenses = await db.expenses.find(
        {"user_id": user.user_id, "month": month}, {"_id": 0}
    ).to_list(5000)
    return expenses


@api_router.post("/finance/expenses", status_code=201)
async def create_expense(
    data: ExpenseCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    resolved_category_name = await resolve_user_category_name(
        user.user_id, data.category, expected_type="expense"
    )
    if not resolved_category_name:
        raise HTTPException(status_code=400, detail="Invalid category")

    expense = {
        "expense_id": f"exp_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "name": data.name,
        "amount": data.amount,
        "method_id": data.method_id,
        "category": resolved_category_name,
        "subcategory": data.subcategory,
        "month": data.month,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.expenses.insert_one(expense)
    return sanitize_mongo_document(expense)


@api_router.put("/finance/expenses/{expense_id}")
async def update_expense(
    expense_id: str,
    data: ExpenseUpdate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)

    resolved_category_name = await resolve_user_category_name(
        user.user_id, data.category, expected_type="expense"
    )
    if not resolved_category_name:
        raise HTTPException(status_code=400, detail="Invalid category")

    update_result = await db.expenses.update_one(
        {"expense_id": expense_id, "user_id": user.user_id},
        {
            "$set": {
                "name": data.name,
                "amount": data.amount,
                "method_id": data.method_id,
                "category": resolved_category_name,
                "subcategory": data.subcategory,
                "month": data.month,
            }
        },
    )

    if update_result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")

    expense = await db.expenses.find_one(
        {"expense_id": expense_id, "user_id": user.user_id}, {"_id": 0}
    )
    return expense


@api_router.delete("/finance/expenses/{expense_id}")
async def delete_expense(
    expense_id: str,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    result = await db.expenses.delete_one(
        {"expense_id": expense_id, "user_id": user.user_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    return {"message": "Deleted"}


# Incomes
@api_router.get("/finance/incomes")
async def get_incomes(
    month: str,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    incomes = await db.incomes.find(
        {"user_id": user.user_id, "month": month}, {"_id": 0}
    ).to_list(5000)
    return incomes


@api_router.post("/finance/incomes", status_code=201)
async def create_income(
    data: IncomeCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    resolved_category_name = await resolve_user_category_name(
        user.user_id, data.category, expected_type="income"
    )
    if not resolved_category_name:
        raise HTTPException(status_code=400, detail="Invalid income category")

    income = {
        "income_id": f"inc_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "name": data.name,
        "amount": data.amount,
        "category": resolved_category_name,
        "month": data.month,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.incomes.insert_one(income)
    return sanitize_mongo_document(income)


@api_router.delete("/finance/incomes/{income_id}")
async def delete_income(
    income_id: str,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    result = await db.incomes.delete_one(
        {"income_id": income_id, "user_id": user.user_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Income not found")
    return {"message": "Deleted"}


# Savings
@api_router.get("/finance/savings")
async def get_savings(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    savings = await db.savings.find({"user_id": user.user_id}, {"_id": 0}).to_list(100)
    return savings


@api_router.post("/finance/savings", status_code=201)
async def create_savings(
    data: SavingsCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    savings = {
        "savings_id": f"sav_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "name": data.name,
        "type": data.type,
        "amount": data.amount,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.savings.insert_one(savings)
    return sanitize_mongo_document(savings)


@api_router.put("/finance/savings/{savings_id}")
async def update_savings(
    savings_id: str,
    amount: float,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    result = await db.savings.update_one(
        {"savings_id": savings_id, "user_id": user.user_id},
        {
            "$set": {
                "amount": amount,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Savings not found")
    updated = await db.savings.find_one({"savings_id": savings_id}, {"_id": 0})
    return updated


# Summary
@api_router.get("/finance/summary")
async def get_summary(
    month: str,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)

    # Get incomes
    incomes = await db.incomes.find(
        {"user_id": user.user_id, "month": month}, {"_id": 0}
    ).to_list(1000)
    total_income = sum(i["amount"] for i in incomes)

    # Get expenses
    expenses = await db.expenses.find(
        {"user_id": user.user_id, "month": month}, {"_id": 0}
    ).to_list(1000)
    total_expenses = sum(e["amount"] for e in expenses)

    # Category breakdown
    category_breakdown = {}
    for expense in expenses:
        cat = expense["category"]
        category_breakdown[cat] = category_breakdown.get(cat, 0) + expense["amount"]

    return {
        "month": month,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "balance": total_income - total_expenses,
        "category_breakdown": category_breakdown,
    }


@api_router.post("/finance/invoice-reader/jobs", status_code=202)
async def create_invoice_reader_job(
    requested_month: str = Form(...),
    file: UploadFile = File(...),
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)

    if not re.match(r"^\d{4}-\d{2}$", requested_month or ""):
        raise HTTPException(status_code=400, detail="Mês inválido. Use YYYY-MM")

    if (file.content_type or "").lower() not in {
        "application/pdf",
        "application/x-pdf",
    } and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Arquivo PDF vazio")

    now_iso = datetime.now(timezone.utc).isoformat()
    job = {
        "job_id": f"invjob_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "status": "queued",
        "source_type": "credit_card_pdf",
        "filename": file.filename or "fatura.pdf",
        "requested_month": requested_month,
        "bank_name": None,
        "card_suffix": None,
        "category_name": None,
        "expected_total": None,
        "parsed_total": None,
        "parsed_count": 0,
        "created_expense_ids": [],
        "errors": [],
        "started_at": None,
        "finished_at": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.invoice_reader_jobs.insert_one(job)
    asyncio.create_task(
        process_invoice_reader_job(
            job["job_id"], user.user_id, requested_month, job["filename"], pdf_bytes
        )
    )
    return sanitize_mongo_document(job)


@api_router.get("/finance/invoice-reader/jobs")
async def get_invoice_reader_jobs(
    limit: int = Query(20, ge=1, le=100),
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    await cleanup_expired_invoice_jobs(user.user_id)
    jobs = await db.invoice_reader_jobs.find(
        {"user_id": user.user_id}, {"_id": 0}
    ).to_list(limit)
    jobs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return jobs[:limit]

    habits = []
    for i, h in enumerate(default_habits):
        habit = {
            "habit_id": f"habit_{uuid.uuid4().hex[:12]}",
            "user_id": user.user_id,
            "name": h["name"],
            "color": h["color"],
            "icon": h["icon"],
            "start_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=30)).strftime(
                "%Y-%m-%d"
            ),
            "frequency": "daily",
            "order": i,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        habits.append(habit)

    await db.habits.insert_many(habits)

    return {"message": f"Created {len(habits)} default habits"}


# ============ COMPLETIONS ENDPOINTS ============


@api_router.get("/completions")
async def get_completions(
    year: int,
    month: int,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    """Get completions for a month"""
    user = await get_current_user(session_token, authorization)

    # Date range for month
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year+1}-01-01"
    else:
        end_date = f"{year}-{month+1:02d}-01"

    completions = await db.habit_completions.find(
        {"user_id": user.user_id, "date": {"$gte": start_date, "$lt": end_date}},
        {"_id": 0},
    ).to_list(1000)

    # Parse datetimes
    for comp in completions:
        if isinstance(comp.get("completed_at"), str):
            comp["completed_at"] = datetime.fromisoformat(comp["completed_at"])

    return completions


@api_router.post("/completions/toggle")
async def toggle_completion(
    data: CompletionToggle,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    """Toggle habit completion for a date"""
    user = await get_current_user(session_token, authorization)

    # Verify habit ownership
    habit = await db.habits.find_one(
        {"habit_id": data.habit_id, "user_id": user.user_id}, {"_id": 0}
    )
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    user_doc = await db.users.find_one(
        {"user_id": user.user_id}, {"_id": 0, "settings": 1}
    )
    today_key = get_local_day_key(get_user_timezone(user_doc or {}))
    selected_date = parse_day_key(data.date)
    if data.date != today_key:
        raise HTTPException(
            status_code=400, detail="Você só pode concluir objetivos no dia de hoje"
        )

    habit_start = habit.get("start_date")
    habit_end = habit.get("end_date")
    if habit_start and selected_date < parse_day_key(habit_start):
        raise HTTPException(
            status_code=400, detail="Date is before this objective period"
        )
    if habit_end and selected_date > parse_day_key(habit_end):
        raise HTTPException(
            status_code=400, detail="Date is after this objective period"
        )
    if not is_habit_scheduled_for_date(habit, selected_date):
        raise HTTPException(
            status_code=400, detail="Este objetivo não está programado para este dia"
        )

    # Check if completion exists
    existing = await db.habit_completions.find_one(
        {"habit_id": data.habit_id, "user_id": user.user_id, "date": data.date},
        {"_id": 0},
    )

    if existing:
        # Toggle
        new_completed = not existing["completed"]
        await db.habit_completions.update_one(
            {"completion_id": existing["completion_id"]},
            {
                "$set": {
                    "completed": new_completed,
                    "completed_at": (
                        datetime.now(timezone.utc).isoformat()
                        if new_completed
                        else None
                    ),
                }
            },
        )
        return {"completed": new_completed}
    else:
        # Create new completion
        completion = {
            "completion_id": f"comp_{uuid.uuid4().hex[:12]}",
            "habit_id": data.habit_id,
            "user_id": user.user_id,
            "date": data.date,
            "completed": True,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.habit_completions.insert_one(completion)
        return {"completed": True}


# ============ NOTIFICATIONS ENDPOINTS ============


@api_router.get("/notifications")
async def get_notifications(
    limit: int = Query(30, ge=1, le=100),
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    items = (
        await db.notifications.find({"user_id": user.user_id}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )
    return items


@api_router.post("/notifications/refresh")
async def refresh_notifications(
    send_email: bool = True,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    user = await get_current_user(session_token, authorization)
    user_doc = await db.users.find_one(
        {"user_id": user.user_id}, {"_id": 0, "settings": 1}
    )
    tz_name = get_user_timezone(user_doc or {})

    try:
        now_local = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now_local = datetime.now(timezone.utc)

    start_key = now_local.replace(day=1).strftime("%Y-%m-%d")
    end_key = (now_local + timedelta(days=1)).strftime("%Y-%m-%d")

    habits = await db.habits.find({"user_id": user.user_id}, {"_id": 0}).to_list(1000)
    completions = await db.habit_completions.find(
        {"user_id": user.user_id, "date": {"$gte": start_key, "$lt": end_key}},
        {"_id": 0},
    ).to_list(200)

    generated = compose_goal_notifications(habits, completions, now_local)
    new_items = await persist_notifications(user.user_id, generated)

    email_sent = False
    if send_email and new_items:
        email_sent = await dispatch_email_notifications(user, new_items)

    items = (
        await db.notifications.find({"user_id": user.user_id}, {"_id": 0})
        .sort("created_at", -1)
        .limit(30)
        .to_list(30)
    )
    return {"items": items, "email_sent": email_sent, "created_count": len(new_items)}


# ============ ADMIN ENDPOINTS ============


@api_router.get("/admin/users")
async def admin_get_users(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    """Get all users (admin only)"""
    await require_admin_user(session_token, authorization)

    users = await db.users.find({}, {"_id": 0}).to_list(1000)

    for u in users:
        if isinstance(u.get("created_at"), str):
            u["created_at"] = datetime.fromisoformat(u["created_at"])

    return users


@api_router.get("/admin/stats")
async def admin_get_stats(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    """Get platform stats (admin only)"""
    await require_admin_user(session_token, authorization)

    total_users = await db.users.count_documents({})
    total_habits = await db.habits.count_documents({})
    total_completions = await db.habit_completions.count_documents({"completed": True})

    return {
        "total_users": total_users,
        "total_habits": total_habits,
        "total_completions": total_completions,
    }


@api_router.get("/admin/quotes")
async def admin_list_quotes(
    q: str = "",
    mode: Optional[Literal["neutral", "kolbe"]] = None,
    active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    await require_admin_user(session_token, authorization)

    query = {}
    if mode:
        query["mode"] = mode
    if active is not None:
        query["active"] = active
    if q:
        query["$or"] = [
            {"text": {"$regex": re.escape(q), "$options": "i"}},
            {"author": {"$regex": re.escape(q), "$options": "i"}},
        ]

    total = await db.quotes.count_documents(query)
    cursor = (
        db.quotes.find(query, {"_id": 0})
        .sort("updated_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = await cursor.to_list(page_size)

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@api_router.post("/admin/quotes", status_code=201)
async def admin_create_quote(
    payload: QuoteCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    await require_admin_user(session_token, authorization)

    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    if not payload.author.strip():
        raise HTTPException(status_code=400, detail="author is required")

    quote = {
        "id": f"quote_{uuid.uuid4().hex[:12]}",
        "mode": payload.mode,
        "text": payload.text.strip(),
        "author": payload.author.strip(),
        "tags": [t.strip() for t in payload.tags if t.strip()],
        "active": payload.active,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "dedupe_key": normalize_quote_key(payload.mode, payload.text, payload.author),
    }
    await db.quotes.insert_one(quote)
    quote.pop("dedupe_key", None)
    return sanitize_mongo_document(quote)


@api_router.put("/admin/quotes/{quote_id}")
async def admin_update_quote(
    quote_id: str,
    payload: QuoteCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    await require_admin_user(session_token, authorization)

    update = {
        "mode": payload.mode,
        "text": payload.text.strip(),
        "author": payload.author.strip(),
        "tags": [t.strip() for t in payload.tags if t.strip()],
        "active": payload.active,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "dedupe_key": normalize_quote_key(payload.mode, payload.text, payload.author),
    }

    result = await db.quotes.update_one({"id": quote_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Quote not found")

    quote = await db.quotes.find_one({"id": quote_id}, {"_id": 0, "dedupe_key": 0})
    return quote


@api_router.delete("/admin/quotes/{quote_id}")
async def admin_delete_quote(
    quote_id: str,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    await require_admin_user(session_token, authorization)
    result = await db.quotes.delete_one({"id": quote_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Quote not found")
    return {"deleted": [quote_id], "failed": []}


@api_router.post("/admin/quotes/bulk-delete")
async def admin_bulk_delete_quotes(
    payload: QuoteBulkDeletePayload,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    await require_admin_user(session_token, authorization)

    ids = [quote_id for quote_id in payload.ids if quote_id]
    if not ids:
        raise HTTPException(status_code=400, detail="No ids provided")

    existing = await db.quotes.find({"id": {"$in": ids}}, {"_id": 0, "id": 1}).to_list(
        len(ids)
    )
    existing_ids = {item["id"] for item in existing}
    failed = [
        {"id": quote_id, "reason": "not_found"}
        for quote_id in ids
        if quote_id not in existing_ids
    ]

    if existing_ids:
        await db.quotes.delete_many({"id": {"$in": list(existing_ids)}})

    return {"deleted": list(existing_ids), "failed": failed}


@api_router.post("/admin/quotes/import")
async def admin_import_quotes(
    payload: QuoteImportPayload,
    strict: bool = False,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    await require_admin_user(session_token, authorization)

    if payload.version != 1:
        raise HTTPException(status_code=400, detail="Unsupported version")

    report = {
        "total_lidas": len(payload.items),
        "criadas": 0,
        "ignoradas_duplicadas": 0,
        "invalidas": 0,
        "erros": [],
    }

    existing_docs = await db.quotes.find({}, {"_id": 0, "dedupe_key": 1}).to_list(10000)
    existing_keys = {
        doc.get("dedupe_key") for doc in existing_docs if doc.get("dedupe_key")
    }

    valid_docs = []
    for idx, item in enumerate(payload.items):
        errors = []
        if item.mode not in ["neutral", "kolbe"]:
            errors.append("mode inválido")
        if not item.text.strip():
            errors.append("text obrigatório")
        author = item.author.strip() or "Desconhecido"
        if not author:
            errors.append("author obrigatório")

        if errors:
            report["invalidas"] += 1
            report["erros"].append({"index": idx, "erros": errors})
            continue

        key = normalize_quote_key(item.mode, item.text, author)
        if key in existing_keys:
            report["ignoradas_duplicadas"] += 1
            continue

        quote = {
            "id": f"quote_{uuid.uuid4().hex[:12]}",
            "mode": item.mode,
            "text": item.text.strip(),
            "author": author,
            "tags": [t.strip() for t in item.tags if t.strip()],
            "active": item.active,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "dedupe_key": key,
        }
        valid_docs.append(quote)
        existing_keys.add(key)

    if strict and report["invalidas"] > 0:
        return report

    if valid_docs:
        await db.quotes.insert_many(valid_docs)
        report["criadas"] = len(valid_docs)

    return report


@api_router.post("/admin/quotes/import-seed")
async def admin_import_seed_quotes(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    await require_admin_user(session_token, authorization)

    seed_path = ROOT_DIR / "seed_quotes.json"
    if not seed_path.exists():
        raise HTTPException(status_code=404, detail="Seed file not found")

    try:
        data = json.loads(seed_path.read_text())
        payload = QuoteImportPayload(**data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid seed JSON: {exc}")

    return await admin_import_quotes(payload, False, session_token, authorization)


@api_router.get("/health")
async def health_check():
    timestamp = datetime.now(timezone.utc).isoformat()
    checks = {"mongo": "ok", "collections": "ok"}

    try:
        await db.command("ping")
    except Exception as exc:
        checks["mongo"] = f"error: {exc}"
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "timestamp": timestamp, "checks": checks},
        )

    try:
        await db.financial_categories.estimated_document_count()
        await db.expenses.estimated_document_count()
        await db.financial_methods.estimated_document_count()
    except Exception as exc:
        checks["collections"] = f"error: {exc}"
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "timestamp": timestamp, "checks": checks},
        )

    return {"status": "ok", "timestamp": timestamp, "checks": checks}


# Include the router in the main app
app.include_router(api_router)

DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://localhost:5173,https://kolbeplanner.space,https://www.kolbeplanner.space"


def _parse_cors_origins(raw_origins: str) -> list[str]:
    """Normalize CORS origins from env to avoid mismatch issues."""
    origins = []
    for origin in raw_origins.split(","):
        value = origin.strip()
        if not value:
            continue
        if value != "*":
            value = value.rstrip("/")
        origins.append(value)

    return origins


cors_origins = _parse_cors_origins(os.environ.get("CORS_ORIGINS", DEFAULT_CORS_ORIGINS))
if not cors_origins:
    cors_origins = _parse_cors_origins(DEFAULT_CORS_ORIGINS)
allow_all_origins = "*" in cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[] if allow_all_origins else cors_origins,
    allow_origin_regex="https?://.*" if allow_all_origins else None,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def create_database_indexes():
    """Create MongoDB indexes used by frequent finance queries."""
    await db.expenses.create_index([("user_id", 1), ("month", 1)])
    await db.expenses.create_index([("user_id", 1), ("category", 1)])
    await ensure_financial_category_indexes()
    await db.financial_categories.create_index(
        [("user_id", 1), ("type", 1), ("name_key", 1)], unique=True
    )
    await db.incomes.create_index([("user_id", 1), ("month", 1)])
    await db.financial_methods.create_index([("user_id", 1), ("name", 1)])
    await db.invoice_reader_jobs.create_index([("user_id", 1), ("created_at", -1)])
    await db.invoice_reader_jobs.create_index([("job_id", 1)], unique=True)
    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
    await db.notifications.create_index(
        [("user_id", 1), ("dedupe_key", 1)], unique=True
    )


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
