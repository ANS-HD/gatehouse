from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=32_000)

    @field_validator("content")
    @classmethod
    def nonempty_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank")
        return value


class ChatInput(BaseModel):
    key_id: str = Field(min_length=1, max_length=128)
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)
    max_output_tokens: int = Field(default=2048, ge=16, le=8192)
    stream: bool = True

    @model_validator(mode="after")
    def user_message_boundaries(self) -> Self:
        if self.messages[0].role != "user" or self.messages[-1].role != "user":
            raise ValueError("Conversation must start and end with a user message")
        return self
