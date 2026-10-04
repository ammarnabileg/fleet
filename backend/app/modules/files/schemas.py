from pydantic import BaseModel


class FileOut(BaseModel):
    sha256: str
    size_bytes: int
    content_type: str
