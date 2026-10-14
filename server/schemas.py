import re

from pydantic import BaseModel, Field, field_validator

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class Phrase(BaseModel):
    id: str
    text: str = Field(min_length=1, max_length=60)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError("id が不正です")
        return v


class PhraseList(BaseModel):
    phrases: list[Phrase] = Field(min_length=1, max_length=50)

    @field_validator("phrases")
    @classmethod
    def _unique(cls, v: list[Phrase]) -> list[Phrase]:
        if len({p.id for p in v}) != len(v):
            raise ValueError("id が重複しています")
        return v


class ClipMeta(BaseModel):
    phrase_id: str
    session_id: str
    source: str = "collect"  # collect | use
    fps_measured: float | None = Field(default=None, ge=0, le=120)
    frame_count: int | None = Field(default=None, ge=0, le=600)

    @field_validator("phrase_id", "session_id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError("id が不正です")
        return v

    @field_validator("source")
    @classmethod
    def _source(cls, v: str) -> str:
        if v not in ("collect", "use"):
            raise ValueError("source が不正です")
        return v
