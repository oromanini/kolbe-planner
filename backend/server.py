from fastapi import FastAPI, APIRouter, HTTPException, Cookie, Response, Header, Query
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
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

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
    frequency: Literal["daily", "weekdays"] = "daily"
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
    frequency: Literal["daily", "weekdays"] = "daily"

class HabitUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    frequency: Optional[Literal["daily", "weekdays"]] = None
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


# ============ AUTH HELPER ============

async def get_current_user(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
) -> User:
    """Get current user from session token (cookie or header)"""
    token = session_token
    
    # Fallback to Authorization header
    if not token and authorization:
        if authorization.startswith('Bearer '):
            token = authorization[7:]
        else:
            token = authorization
    
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Find session
    session_doc = await db.user_sessions.find_one(
        {"session_token": token},
        {"_id": 0}
    )
    
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
    user_doc = await db.users.find_one(
        {"user_id": session_doc["user_id"]},
        {"_id": 0}
    )
    
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Parse datetime
    if isinstance(user_doc.get('created_at'), str):
        user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
    user_doc['settings'] = normalize_user_settings(user_doc.get('settings'))

    return User(**user_doc)




def normalize_user_settings(settings: Optional[dict]) -> dict:
    normalized = {"kolbe_mode_enabled": False}
    if isinstance(settings, dict):
        normalized["kolbe_mode_enabled"] = bool(settings.get("kolbe_mode_enabled", False))
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
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD") from exc


def ensure_period_is_valid(start_date: str, end_date: str, min_date: Optional[str] = None):
    start = parse_day_key(start_date)
    end = parse_day_key(end_date)
    if end < start:
        raise HTTPException(status_code=400, detail="End date must be greater than or equal to start date")
    if min_date:
        minimum = parse_day_key(min_date)
        if start < minimum:
            raise HTTPException(status_code=400, detail="Start date cannot be in the past")


def is_habit_scheduled_for_date(habit: dict, selected_date: datetime) -> bool:
    frequency = habit.get("frequency") or "daily"
    if frequency == "weekdays":
        return selected_date.weekday() < 5
    return True


async def require_admin_user(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
) -> User:
    user = await get_current_user(session_token, authorization)
    admin_emails = [email.strip().lower() for email in os.environ.get("ADMIN_EMAILS", "oscar.romanini.jr@gmail.com").split(",") if email.strip()]
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
    await db.users.insert_one({
        "user_id": user_id,
        "email": request.email,
        "name": request.name,
        "password_hash": password_hash,
        "picture": None,
        "onboarding_completed": False,
        "settings": {"kolbe_mode_enabled": False},
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Create session
    session_token = f"jwt_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    await db.user_sessions.insert_one({
        "session_token": session_token,
        "user_id": user_id,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7*24*60*60
    )
    
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if isinstance(user_doc.get('created_at'), str):
        user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
    user_doc['settings'] = normalize_user_settings(user_doc.get('settings'))

    return User(**user_doc)


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
    
    await db.user_sessions.insert_one({
        "session_token": session_token,
        "user_id": user_doc["user_id"],
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7*24*60*60
    )
    
    if isinstance(user_doc.get('created_at'), str):
        user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
    user_doc['settings'] = normalize_user_settings(user_doc.get('settings'))

    return User(**user_doc)


@api_router.get("/auth/me")
async def get_me(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
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
    authorization: Optional[str] = Header(None)
):
    """Mark onboarding as completed"""
    user = await get_current_user(session_token, authorization)

    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"onboarding_completed": True}}
    )

    return {"message": "Onboarding completed"}


@api_router.put("/users/settings")
async def update_user_settings(
    payload: UserSettingsUpdate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)

    current_settings = normalize_user_settings(user.settings)
    new_settings = {
        **current_settings,
        "kolbe_mode_enabled": payload.kolbe_mode_enabled
    }

    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"settings": new_settings}}
    )

    return {"settings": new_settings}


@api_router.get("/quotes/daily")
async def get_daily_quote(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    mode = "kolbe" if user.settings.get("kolbe_mode_enabled") else "neutral"
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "settings": 1}) or {}
    timezone_name = get_user_timezone(user_doc)
    local_day = get_local_day_key(timezone_name)

    stored = await db.user_daily_quotes.find_one(
        {"user_id": user.user_id, "local_day": local_day, "mode": mode},
        {"_id": 0}
    )
    if stored:
        quote = await db.quotes.find_one({"id": stored["quote_id"], "active": True}, {"_id": 0})
        if quote:
            return {"quote": quote, "mode": mode, "local_day": local_day}

    quotes = await db.quotes.find({"mode": mode, "active": True}, {"_id": 0}).to_list(2000)
    selected_mode = mode
    if not quotes and mode == "kolbe":
        quotes = await db.quotes.find({"mode": "neutral", "active": True}, {"_id": 0}).to_list(2000)
        selected_mode = "neutral"

    if not quotes:
        return {"quote": None, "mode": selected_mode, "local_day": local_day}

    seed_key = f"{user.user_id}:{local_day}:{selected_mode}".encode()
    seed = int(hashlib.sha256(seed_key).hexdigest(), 16)
    quote = quotes[seed % len(quotes)]

    await db.user_daily_quotes.update_one(
        {"user_id": user.user_id, "local_day": local_day, "mode": selected_mode},
        {"$set": {"quote_id": quote["id"], "updated_at": datetime.now(timezone.utc).isoformat()},
         "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )

    return {"quote": quote, "mode": selected_mode, "local_day": local_day}


# ============ HABITS ENDPOINTS ============

@api_router.get("/habits", response_model=List[Habit])
async def get_habits(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    """Get user's habits"""
    user = await get_current_user(session_token, authorization)
    
    habits = await db.habits.find(
        {"user_id": user.user_id},
        {"_id": 0}
    ).sort("order", 1).to_list(100)
    
    # Parse datetimes
    for habit in habits:
        if isinstance(habit.get('created_at'), str):
            habit['created_at'] = datetime.fromisoformat(habit['created_at'])
        start_date = habit.get('start_date')
        if not start_date:
            start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            habit['start_date'] = start_date
        if not habit.get('end_date'):
            habit['end_date'] = start_date
        if not habit.get('frequency'):
            habit['frequency'] = 'daily'
    
    return habits


@api_router.post("/habits", response_model=Habit, status_code=201)
async def create_habit(
    habit_data: HabitCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    """Create a new habit (max 10)"""
    user = await get_current_user(session_token, authorization)
    
    # Check limit
    count = await db.habits.count_documents({"user_id": user.user_id})
    if count >= 10:
        raise HTTPException(status_code=400, detail="Maximum 10 habits allowed")
    
    # Get next order
    last_habit = await db.habits.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "order": 1},
        sort=[("order", -1)]
    )
    next_order = (last_habit["order"] + 1) if last_habit else 0
    
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "settings": 1})
    today_key = get_local_day_key(get_user_timezone(user_doc or {}))
    ensure_period_is_valid(habit_data.start_date, habit_data.end_date, today_key)

    habit = Habit(
        habit_id=f"habit_{uuid.uuid4().hex[:12]}",
        user_id=user.user_id,
        name=habit_data.name,
        color=habit_data.color,
        icon=habit_data.icon,
        start_date=habit_data.start_date,
        end_date=habit_data.end_date,
        frequency=habit_data.frequency,
        order=next_order,
        created_at=datetime.now(timezone.utc)
    )
    
    doc = habit.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.habits.insert_one(doc)
    
    return habit


@api_router.put("/habits/{habit_id}", response_model=Habit)
async def update_habit(
    habit_id: str,
    habit_data: HabitUpdate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    """Update a habit"""
    user = await get_current_user(session_token, authorization)
    
    # Check ownership
    habit = await db.habits.find_one(
        {"habit_id": habit_id, "user_id": user.user_id},
        {"_id": 0}
    )
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    
    # Update
    update_data = {k: v for k, v in habit_data.model_dump().items() if v is not None}
    if update_data:
        user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "settings": 1})
        today_key = get_local_day_key(get_user_timezone(user_doc or {}))
        next_start_date = update_data.get("start_date", habit.get("start_date", today_key))
        next_end_date = update_data.get("end_date", habit.get("end_date", next_start_date))
        ensure_period_is_valid(next_start_date, next_end_date, today_key)

        await db.habits.update_one(
            {"habit_id": habit_id},
            {"$set": update_data}
        )
    
    # Return updated
    updated_habit = await db.habits.find_one({"habit_id": habit_id}, {"_id": 0})
    if isinstance(updated_habit.get('created_at'), str):
        updated_habit['created_at'] = datetime.fromisoformat(updated_habit['created_at'])
    if not updated_habit.get('start_date'):
        updated_habit['start_date'] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not updated_habit.get('end_date'):
        updated_habit['end_date'] = updated_habit['start_date']
    if not updated_habit.get('frequency'):
        updated_habit['frequency'] = 'daily'

    return Habit(**updated_habit)


@api_router.delete("/habits/{habit_id}")
async def delete_habit(
    habit_id: str,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    """Delete a habit and its completions"""
    user = await get_current_user(session_token, authorization)
    
    result = await db.habits.delete_one(
        {"habit_id": habit_id, "user_id": user.user_id}
    )
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Habit not found")
    
    # Delete completions
    await db.habit_completions.delete_many({"habit_id": habit_id})
    
    return {"message": "Habit deleted"}


@api_router.post("/habits/initialize-defaults")
async def initialize_default_habits(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
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
    existing_methods = await db.financial_methods.find({"user_id": user_id}, {"_id": 0, "name": 1}).to_list(200)
    existing_names = {normalize_method_name(method.get("name", "")) for method in existing_methods}

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
        if index_meta.get("unique") and keys == [("user_id", 1)]:
            await db.financial_categories.drop_index(index_name)


class CategoryCreate(BaseModel):
    name: str

class CategoryUpdate(BaseModel):
    name: str


async def resolve_user_category_name(user_id: str, raw_category: str) -> Optional[str]:
    """Resolve category payload to the canonical category name stored for the user."""
    category_value = (raw_category or "").strip()
    if not category_value:
        return None

    by_id = await db.financial_categories.find_one(
        {"user_id": user_id, "category_id": category_value},
        {"_id": 0, "name": 1},
    )
    if by_id and by_id.get("name"):
        return by_id["name"]

    normalized_key = normalize_category_key(category_value)
    by_key = await db.financial_categories.find_one(
        {"user_id": user_id, "name_key": normalized_key},
        {"_id": 0, "name": 1},
    )
    if by_key and by_key.get("name"):
        return by_key["name"]

    by_exact_name = await db.financial_categories.find_one(
        {"user_id": user_id, "name": category_value},
        {"_id": 0, "name": 1},
    )
    if by_exact_name and by_exact_name.get("name"):
        return by_exact_name["name"]

    return None


# ============ FINANCIAL ENDPOINTS ============

# Methods
@api_router.get("/finance/methods")
async def get_methods(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    await ensure_default_financial_methods(user.user_id)
    methods = await db.financial_methods.find({"user_id": user.user_id}, {"_id": 0}).to_list(100)
    return methods

@api_router.post("/finance/methods", status_code=201)
async def create_method(
    data: MethodCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)

    existing_methods = await db.financial_methods.find({"user_id": user.user_id}, {"_id": 0, "name": 1}).to_list(200)
    method_exists = any(normalize_method_name(method.get("name", "")) == normalize_method_name(data.name) for method in existing_methods)
    if method_exists:
        raise HTTPException(status_code=409, detail="Method already exists")

    method = {
        "method_id": f"method_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "name": data.name,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.financial_methods.insert_one(method)
    return sanitize_mongo_document(method)

# Categories
@api_router.get("/finance/categories")
async def get_categories(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    categories = await db.financial_categories.find({"user_id": user.user_id}, {"_id": 0}).to_list(100)
    return categories

@api_router.post("/finance/categories", status_code=201)
async def create_category(
    data: CategoryCreate,
    response: Response = None,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    normalized_name = normalize_category_name(data.name)
    normalized_key = normalize_category_key(data.name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Category name is required")

    existing_categories = await db.financial_categories.find({"user_id": user.user_id}, {"_id": 0}).to_list(300)
    existing = next((category for category in existing_categories if normalize_category_key(category.get("name", "")) == normalized_key), None)
    if existing:
        if response is not None:
            response.status_code = 200
        return existing

    category = {
        "category_id": f"cat_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "name": normalized_name,
        "name_key": normalized_key,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    try:
        await db.financial_categories.insert_one(category)
    except DuplicateKeyError:
        duplicate = await db.financial_categories.find_one(
            {"user_id": user.user_id, "name_key": normalized_key},
            {"_id": 0}
        )
        if duplicate:
            if response is not None:
                response.status_code = 200
            return duplicate
        logger.exception("Duplicate key while creating category %s for user %s", normalized_name, user.user_id)
        raise HTTPException(status_code=409, detail="Category already exists")
    return sanitize_mongo_document(category)

@api_router.put("/finance/categories/{category_id}")
async def update_category(
    category_id: str,
    data: CategoryUpdate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    normalized_name = normalize_category_name(data.name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Category name is required")

    existing = await db.financial_categories.find_one(
        {"category_id": category_id, "user_id": user.user_id},
        {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Category not found")

    normalized_key = normalize_category_key(data.name)
    if normalize_category_key(existing.get("name", "")) != normalized_key:
        existing_categories = await db.financial_categories.find({"user_id": user.user_id}, {"_id": 0, "category_id": 1, "name": 1}).to_list(300)
        duplicate = next((category for category in existing_categories if category.get("category_id") != category_id and normalize_category_key(category.get("name", "")) == normalized_key), None)
        if duplicate:
            raise HTTPException(status_code=409, detail="Category already exists")

    try:
        await db.financial_categories.update_one(
            {"category_id": category_id, "user_id": user.user_id},
            {"$set": {"name": normalized_name, "name_key": normalized_key}}
        )
    except DuplicateKeyError:
        duplicate = await db.financial_categories.find_one(
            {"user_id": user.user_id, "name_key": normalized_key, "category_id": {"$ne": category_id}},
            {"_id": 0, "category_id": 1}
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
        await db.expenses.update_many(
            {"user_id": user.user_id, "category": existing.get("name")},
            {"$set": {"category": normalized_name}}
        )

    category = await db.financial_categories.find_one(
        {"category_id": category_id, "user_id": user.user_id},
        {"_id": 0}
    )
    return category

@api_router.delete("/finance/categories/{category_id}")
async def delete_category(
    category_id: str,
    force: bool = False,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    category = await db.financial_categories.find_one(
        {"category_id": category_id, "user_id": user.user_id},
        {"_id": 0}
    )
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    linked_items_count = await db.expenses.count_documents({
        "user_id": user.user_id,
        "category": category["name"]
    })

    if linked_items_count > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Category has linked items",
                "linked_items_count": linked_items_count
            }
        )

    await db.financial_categories.delete_one({"category_id": category_id, "user_id": user.user_id})
    if linked_items_count > 0:
        await db.expenses.delete_many({"user_id": user.user_id, "category": category["name"]})

    return {"message": "Category deleted", "deleted_expenses": linked_items_count}

# Expenses
@api_router.get("/finance/expenses")
async def get_expenses(
    month: str,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    expenses = await db.expenses.find(
        {"user_id": user.user_id, "month": month},
        {"_id": 0}
    ).to_list(1000)
    return expenses

@api_router.post("/finance/expenses", status_code=201)
async def create_expense(
    data: ExpenseCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    resolved_category_name = await resolve_user_category_name(user.user_id, data.category)
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
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.expenses.insert_one(expense)
    return sanitize_mongo_document(expense)

@api_router.put("/finance/expenses/{expense_id}")
async def update_expense(
    expense_id: str,
    data: ExpenseUpdate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)

    resolved_category_name = await resolve_user_category_name(user.user_id, data.category)
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
        {"expense_id": expense_id, "user_id": user.user_id},
        {"_id": 0}
    )
    return expense

@api_router.delete("/finance/expenses/{expense_id}")
async def delete_expense(
    expense_id: str,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    result = await db.expenses.delete_one({"expense_id": expense_id, "user_id": user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    return {"message": "Deleted"}

# Incomes
@api_router.get("/finance/incomes")
async def get_incomes(
    month: str,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    incomes = await db.incomes.find(
        {"user_id": user.user_id, "month": month},
        {"_id": 0}
    ).to_list(1000)
    return incomes

@api_router.post("/finance/incomes", status_code=201)
async def create_income(
    data: IncomeCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    income = {
        "income_id": f"inc_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "name": data.name,
        "amount": data.amount,
        "month": data.month,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.incomes.insert_one(income)
    return sanitize_mongo_document(income)

@api_router.delete("/finance/incomes/{income_id}")
async def delete_income(
    income_id: str,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    result = await db.incomes.delete_one({"income_id": income_id, "user_id": user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Income not found")
    return {"message": "Deleted"}

# Savings
@api_router.get("/finance/savings")
async def get_savings(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    savings = await db.savings.find({"user_id": user.user_id}, {"_id": 0}).to_list(100)
    return savings

@api_router.post("/finance/savings", status_code=201)
async def create_savings(
    data: SavingsCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    savings = {
        "savings_id": f"sav_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "name": data.name,
        "type": data.type,
        "amount": data.amount,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.savings.insert_one(savings)
    return sanitize_mongo_document(savings)

@api_router.put("/finance/savings/{savings_id}")
async def update_savings(
    savings_id: str,
    amount: float,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    result = await db.savings.update_one(
        {"savings_id": savings_id, "user_id": user.user_id},
        {"$set": {"amount": amount, "updated_at": datetime.now(timezone.utc).isoformat()}}
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
    authorization: Optional[str] = Header(None)
):
    user = await get_current_user(session_token, authorization)
    
    # Get incomes
    incomes = await db.incomes.find({"user_id": user.user_id, "month": month}, {"_id": 0}).to_list(1000)
    total_income = sum(i["amount"] for i in incomes)
    
    # Get expenses
    expenses = await db.expenses.find({"user_id": user.user_id, "month": month}, {"_id": 0}).to_list(1000)
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
        "category_breakdown": category_breakdown
    }

    
    habits = []
    for i, h in enumerate(default_habits):
        habit = {
            "habit_id": f"habit_{uuid.uuid4().hex[:12]}",
            "user_id": user.user_id,
            "name": h["name"],
            "color": h["color"],
            "icon": h["icon"],
            "start_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d"),
            "frequency": "daily",
            "order": i,
            "created_at": datetime.now(timezone.utc).isoformat()
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
    authorization: Optional[str] = Header(None)
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
        {
            "user_id": user.user_id,
            "date": {"$gte": start_date, "$lt": end_date}
        },
        {"_id": 0}
    ).to_list(1000)
    
    # Parse datetimes
    for comp in completions:
        if isinstance(comp.get('completed_at'), str):
            comp['completed_at'] = datetime.fromisoformat(comp['completed_at'])
    
    return completions


@api_router.post("/completions/toggle")
async def toggle_completion(
    data: CompletionToggle,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    """Toggle habit completion for a date"""
    user = await get_current_user(session_token, authorization)
    
    # Verify habit ownership
    habit = await db.habits.find_one(
        {"habit_id": data.habit_id, "user_id": user.user_id},
        {"_id": 0}
    )
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "settings": 1})
    today_key = get_local_day_key(get_user_timezone(user_doc or {}))
    selected_date = parse_day_key(data.date)
    if data.date != today_key:
        raise HTTPException(status_code=400, detail="Você só pode concluir objetivos no dia de hoje")

    habit_start = habit.get("start_date")
    habit_end = habit.get("end_date")
    if habit_start and selected_date < parse_day_key(habit_start):
        raise HTTPException(status_code=400, detail="Date is before this objective period")
    if habit_end and selected_date > parse_day_key(habit_end):
        raise HTTPException(status_code=400, detail="Date is after this objective period")
    if not is_habit_scheduled_for_date(habit, selected_date):
        raise HTTPException(status_code=400, detail="Este objetivo não está programado para este dia")
    
    # Check if completion exists
    existing = await db.habit_completions.find_one(
        {
            "habit_id": data.habit_id,
            "user_id": user.user_id,
            "date": data.date
        },
        {"_id": 0}
    )
    
    if existing:
        # Toggle
        new_completed = not existing["completed"]
        await db.habit_completions.update_one(
            {"completion_id": existing["completion_id"]},
            {
                "$set": {
                    "completed": new_completed,
                    "completed_at": datetime.now(timezone.utc).isoformat() if new_completed else None
                }
            }
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
            "completed_at": datetime.now(timezone.utc).isoformat()
        }
        await db.habit_completions.insert_one(completion)
        return {"completed": True}


# ============ ADMIN ENDPOINTS ============

@api_router.get("/admin/users")
async def admin_get_users(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    """Get all users (admin only)"""
    await require_admin_user(session_token, authorization)

    users = await db.users.find({}, {"_id": 0}).to_list(1000)

    for u in users:
        if isinstance(u.get('created_at'), str):
            u['created_at'] = datetime.fromisoformat(u['created_at'])

    return users


@api_router.get("/admin/stats")
async def admin_get_stats(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    """Get platform stats (admin only)"""
    await require_admin_user(session_token, authorization)

    total_users = await db.users.count_documents({})
    total_habits = await db.habits.count_documents({})
    total_completions = await db.habit_completions.count_documents({"completed": True})

    return {
        "total_users": total_users,
        "total_habits": total_habits,
        "total_completions": total_completions
    }


@api_router.get("/admin/quotes")
async def admin_list_quotes(
    q: str = "",
    mode: Optional[Literal["neutral", "kolbe"]] = None,
    active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
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
            {"author": {"$regex": re.escape(q), "$options": "i"}}
        ]

    total = await db.quotes.count_documents(query)
    cursor = db.quotes.find(query, {"_id": 0}).sort("updated_at", -1).skip((page - 1) * page_size).limit(page_size)
    items = await cursor.to_list(page_size)

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@api_router.post("/admin/quotes", status_code=201)
async def admin_create_quote(
    payload: QuoteCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
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
        "dedupe_key": normalize_quote_key(payload.mode, payload.text, payload.author)
    }
    await db.quotes.insert_one(quote)
    quote.pop("dedupe_key", None)
    return sanitize_mongo_document(quote)


@api_router.put("/admin/quotes/{quote_id}")
async def admin_update_quote(
    quote_id: str,
    payload: QuoteCreate,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    await require_admin_user(session_token, authorization)

    update = {
        "mode": payload.mode,
        "text": payload.text.strip(),
        "author": payload.author.strip(),
        "tags": [t.strip() for t in payload.tags if t.strip()],
        "active": payload.active,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "dedupe_key": normalize_quote_key(payload.mode, payload.text, payload.author)
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
    authorization: Optional[str] = Header(None)
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
    authorization: Optional[str] = Header(None)
):
    await require_admin_user(session_token, authorization)

    ids = [quote_id for quote_id in payload.ids if quote_id]
    if not ids:
        raise HTTPException(status_code=400, detail="No ids provided")

    existing = await db.quotes.find({"id": {"$in": ids}}, {"_id": 0, "id": 1}).to_list(len(ids))
    existing_ids = {item["id"] for item in existing}
    failed = [{"id": quote_id, "reason": "not_found"} for quote_id in ids if quote_id not in existing_ids]

    if existing_ids:
        await db.quotes.delete_many({"id": {"$in": list(existing_ids)}})

    return {"deleted": list(existing_ids), "failed": failed}


@api_router.post("/admin/quotes/import")
async def admin_import_quotes(
    payload: QuoteImportPayload,
    strict: bool = False,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    await require_admin_user(session_token, authorization)

    if payload.version != 1:
        raise HTTPException(status_code=400, detail="Unsupported version")

    report = {
        "total_lidas": len(payload.items),
        "criadas": 0,
        "ignoradas_duplicadas": 0,
        "invalidas": 0,
        "erros": []
    }

    existing_docs = await db.quotes.find({}, {"_id": 0, "dedupe_key": 1}).to_list(10000)
    existing_keys = {doc.get("dedupe_key") for doc in existing_docs if doc.get("dedupe_key")}

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
            "dedupe_key": key
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
    authorization: Optional[str] = Header(None)
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
        raise HTTPException(status_code=503, detail={"status": "degraded", "timestamp": timestamp, "checks": checks})

    try:
        await db.financial_categories.estimated_document_count()
        await db.expenses.estimated_document_count()
        await db.financial_methods.estimated_document_count()
    except Exception as exc:
        checks["collections"] = f"error: {exc}"
        raise HTTPException(status_code=503, detail={"status": "degraded", "timestamp": timestamp, "checks": checks})

    return {"status": "ok", "timestamp": timestamp, "checks": checks}


# Include the router in the main app
app.include_router(api_router)

DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://localhost:5173,https://kolbeplanner.space,https://www.kolbeplanner.space"


def _parse_cors_origins(raw_origins: str) -> list[str]:
    """Normalize CORS origins from env to avoid mismatch issues."""
    origins = []
    for origin in raw_origins.split(','):
        value = origin.strip()
        if not value:
            continue
        if value != "*":
            value = value.rstrip('/')
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
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def create_database_indexes():
    """Create MongoDB indexes used by frequent finance queries."""
    await db.expenses.create_index([("user_id", 1), ("month", 1)])
    await db.expenses.create_index([("user_id", 1), ("category", 1)])
    await ensure_financial_category_indexes()
    await db.financial_categories.create_index([("user_id", 1), ("name_key", 1)], unique=True)
    await db.incomes.create_index([("user_id", 1), ("month", 1)])
    await db.financial_methods.create_index([("user_id", 1), ("name", 1)])

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
