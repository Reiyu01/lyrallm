from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class ChatMessage(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str

class Features(BaseModel):
    web_search: Optional[bool] = False
    image_generation: Optional[bool] = False
    rag_search: Optional[bool] = False
    code_interpreter: Optional[bool] = False

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    top_p: Optional[float] = 1.0
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0
    stop: Optional[List[str]] = None
    features: Optional[Features] = None

    class Config:
        extra = "allow"

class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str

class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage
    meta: Optional[Dict[str, Any]] = None
    routing_info: Optional[Dict[str, Any]] = None

class FeedbackRequest(BaseModel):
    conversation_id: str
    message_id: str
    model: Optional[str] = None
    feedback: str
