import uuid
from datetime import datetime

from pydantic import BaseModel


class AttachmentOut(BaseModel):
    """Metadata of one reference document. Never contains the storage key or any URL: files are only
    served by authenticated endpoints after an authorisation check."""

    id: uuid.UUID
    original_filename: str
    mime_type: str
    file_type: str  # PDF / PPT / PPTX, derived from the detected content type
    size_bytes: int
    uploaded_at: datetime
    previewable: bool
