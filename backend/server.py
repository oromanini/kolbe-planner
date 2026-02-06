from fastapi import FastAPI, APIRouter, HTTPException, Cookie, Response, Header
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import requests

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
    created_at: datetime

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

class SessionRequest(BaseModel):
    session_id: str

class HabitCreate(BaseModel):
    name: str
    color: str
    icon: str = "circle"

class HabitUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    order: Optional[int] = None

class CompletionToggle(BaseModel):
    habit_id: str
    date: str  # YYYY-MM-DD


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
    
    return User(**user_doc)


# ============ AUTH ENDPOINTS ============

@api_router.post("/auth/session")
async def create_session(request: SessionRequest, response: Response):
    """Exchange session_id from Emergent Auth for session_token"""
    
    # Call Emergent Auth API
    try:
        auth_response = requests.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": request.session_id},
            timeout=10
        )
        auth_response.raise_for_status()
        user_data = auth_response.json()
    except Exception as e:
        logging.error(f"Emergent Auth error: {e}")
        raise HTTPException(status_code=401, detail="Invalid session_id")
    
    # Check if user exists
    existing_user = await db.users.find_one(
        {"email": user_data["email"]},
        {"_id": 0}
    )
    
    if existing_user:
        user_id = existing_user["user_id"]
        # Update user data
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "name": user_data["name"],
                "picture": user_data.get("picture")
            }}
        )
    else:
        # Create new user
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": user_data["email"],
            "name": user_data["name"],
            "picture": user_data.get("picture"),
            "onboarding_completed": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    
    # Create session
    session_token = user_data["session_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    await db.user_sessions.insert_one({
        "session_token": session_token,
        "user_id": user_id,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Set httpOnly cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7*24*60*60
    )
    
    # Return user
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if isinstance(user_doc.get('created_at'), str):
        user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
    
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
    
    habit = Habit(
        habit_id=f"habit_{uuid.uuid4().hex[:12]}",
        user_id=user.user_id,
        name=habit_data.name,
        color=habit_data.color,
        icon=habit_data.icon,
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
        await db.habits.update_one(
            {"habit_id": habit_id},
            {"$set": update_data}
        )
    
    # Return updated
    updated_habit = await db.habits.find_one({"habit_id": habit_id}, {"_id": 0})
    if isinstance(updated_habit.get('created_at'), str):
        updated_habit['created_at'] = datetime.fromisoformat(updated_habit['created_at'])
    
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
    
    habits = []
    for i, h in enumerate(default_habits):
        habit = {
            "habit_id": f"habit_{uuid.uuid4().hex[:12]}",
            "user_id": user.user_id,
            "name": h["name"],
            "color": h["color"],
            "icon": h["icon"],
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
    user = await get_current_user(session_token, authorization)
    
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
    user = await get_current_user(session_token, authorization)
    
    total_users = await db.users.count_documents({})
    total_habits = await db.habits.count_documents({})
    total_completions = await db.habit_completions.count_documents({"completed": True})
    
    return {
        "total_users": total_users,
        "total_habits": total_habits,
        "total_completions": total_completions
    }


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
