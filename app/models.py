"""
Pydantic request/response models for all endpoints.

Matches the PWA contract defined in src/lib/api/*.ts and src/lib/auth/auth.ts.
"""

from pydantic import BaseModel, Field

# ---- Auth ----


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthError(BaseModel):
    detail: str


# ---- Conversations ----


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationListResponse(BaseModel):
    conversations: list[ConversationOut]


class CreateConversationRequest(BaseModel):
    title: str = ""


class CreateConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class DeleteConversationResponse(BaseModel):
    deleted: bool


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str


class MessageListResponse(BaseModel):
    messages: list[MessageOut]


# ---- Chat ----


class HistoryMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_id: str
    history: list[HistoryMessage] = Field(default_factory=list)


# ---- Greeting ----


class EnergyInfo(BaseModel):
    power_w: int = 0
    daily_solar_kwh: float = 0.0
    battery_soc: float = 0.0
    energy_import_kwh: float = 0.0
    energy_export_kwh: float = 0.0


class DinnerInfo(BaseModel):
    name: str
    slug: str


class ShoppingInfo(BaseModel):
    monthly_total: float = 0.0
    currency: str = "EUR"


class GreetingResponse(BaseModel):
    greeting: str
    energy: EnergyInfo
    dinner: DinnerInfo | None = None
    shopping: ShoppingInfo | None = None


# ---- Whisper ----


class WhisperResponse(BaseModel):
    text: str
    language: str
    duration: float


# ---- Health ----


class HealthResponse(BaseModel):
    status: str = "ok"
