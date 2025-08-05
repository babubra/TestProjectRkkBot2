# Файл: map_backend/models/models.py

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """
    Базовый класс для всех моделей.
    Содержит общие поля id, created_at, updated_at.
    """

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MapRequest(Base):
    """
    Модель для хранения временных запросов на отображение сделок на карте.
    """

    __tablename__ = "map_requests"

    request_token: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    deals_data_json: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<MapRequest(id={self.id}, user_id={self.user_telegram_id}, "
            f"token='{self.request_token[:8]}...', expires_at='{self.expires_at}')>"
        )