import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.assistant import MODEL, StudyAssistant

app = FastAPI(title="Study Assistant")
assistant = StudyAssistant()


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@app.post("/ask")
def ask(req: AskRequest):
    return assistant.ask(req.question)


@app.post("/ask/stream")
def ask_stream(req: AskRequest):
    return StreamingResponse(assistant.ask_stream(req.question), media_type="text/plain")


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL}


@app.get("/stats")
def stats():
    return assistant.stats()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
