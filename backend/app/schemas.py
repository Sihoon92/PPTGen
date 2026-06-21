from pydantic import BaseModel


class CreateSessionBody(BaseModel):
    title: str | None = None


class RenameBody(BaseModel):
    title: str


class ChatBody(BaseModel):
    content: str
    mode: str = "chat"


class ResumeBody(BaseModel):
    answer: str
