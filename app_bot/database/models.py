import enum
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, BigInteger
from sqlalchemy.types import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Permission(str, enum.Enum):
    """
    Перечисление гранулярных разрешений.
    """

    MANAGE_USERS = "manage_users"  # Право на создание/управление пользователями
    SET_TRIP_LIMITS = "set_visit_limits"  # Право на установку лимитов на выезды
    CREATE_TICKETS = "create_tickets"  # Право на создание заявок
    VIEW_TICKETS = "view_tickets"  # Право на просмотр заявок
    ADD_FILES_FROM_VISIT = (
        "add_files_from_visit"  # Право на добавление файлов к сделке после выезда
    )


class Base(DeclarativeBase):
    """
    Базовый класс для всех моделей.
    Содержит общие поля id, created_at, updated_at.
    """

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    """
    Модель для хранения данных о пользователях бота.
    """

    __tablename__ = "bot_users"

    username: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=False
    )
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    megaplan_user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, unique=True
    )

    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, telegram_id={self.telegram_id}, "
            f"username='{self.username}', permissions={self.permissions})>"
        )

    def has_permission(self, permission: Permission) -> bool:
        """Проверяет, есть ли у пользователя указанное разрешение."""
        return permission.value in self.permissions
