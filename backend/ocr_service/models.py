from sqlalchemy import Column, Boolean, DateTime, Text, BigInteger, String, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from shared.database import Base


class Document(Base):
    __tablename__ = "documents"
    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id    = Column(UUID(as_uuid=True), nullable=False)
    s3_key      = Column(Text, nullable=False)
    is_ocr_done = Column(Boolean, nullable=False, default=False)
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
