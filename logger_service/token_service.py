from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Any, Optional
import logging
from .token_calculator import compute_token_usage

logger = logging.getLogger(__name__)
app = FastAPI(title="Token Calculator Service")


class Message(BaseModel):
    role: str
    content: str


class CalcRequest(BaseModel):
    model_name: str
    messages: List[Message]
    response_obj: Optional[dict] = None
    response_text: Optional[str] = None
    model_config: Optional[dict] = None


@app.post('/calculate')
async def calculate(req: CalcRequest):
    try:
        messages = [m.dict() for m in req.messages]
        result = compute_token_usage(req.response_obj, messages, req.model_name, req.model_config, req.response_text)
        return result
    except Exception as e:
        logger.exception("calculate failed")
        raise HTTPException(status_code=500, detail=str(e))
