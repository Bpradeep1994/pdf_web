from sqlalchemy import Column, String, Boolean, DateTime, Integer, BigInteger, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
from enum import Enum

from shared.database import Base


class DocStatus(str, Enum):
    uploading  = "uploading"
    processing = "processing"
    ready      = "ready"
    error      = "error"


class Document(Base):
    __tablename__ = "documents"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id      = Column(UUID(as_uuid=True), nullable=False, index=True)
    filename      = Column(String(500), nullable=False)
    original_name = Column(String(500), nullable=False)
    s3_key        = Column(Text, nullable=False)
    thumbnail_key = Column(Text)
    file_size     = Column(BigInteger, nullable=False, default=0)
    page_count    = Column(Integer)
    mime_type     = Column(String(100), nullable=False, default="application/pdf")
    status        = Column(SAEnum(DocStatus, name="doc_status"), nullable=False, default=DocStatus.uploading)
    is_ocr_done   = Column(Boolean, nullable=False, default=False)
    is_ai_indexed = Column(Boolean, nullable=False, default=False)
    metadata_     = Column("metadata", JSONB, nullable=False, default={})
    deleted_at    = Column(DateTime(timezone=True))
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    version     = Column(Integer, nullable=False)
    s3_key      = Column(Text, nullable=False)
    file_size   = Column(BigInteger, nullable=False, default=0)
    comment     = Column(Text)
    created_by  = Column(UUID(as_uuid=True), nullable=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class DocumentShare(Base):
    __tablename__ = "document_shares"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    shared_with = Column(UUID(as_uuid=True))
    share_token = Column(String(255), unique=True, index=True)
    permission  = Column(String(20), nullable=False, default="view")
    expires_at  = Column(DateTime(timezone=True))
    created_by  = Column(UUID(as_uuid=True), nullable=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
