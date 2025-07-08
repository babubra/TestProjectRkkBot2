# Файл: app_bot/crm_service/schemas.py

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field, field_validator

from app_bot.config.config import get_env_settings


settings = get_env_settings()
APP_TIMEZONE = timezone(timedelta(hours=settings.APP_TIMEZONE_OFFSET))


class BaseSchema(BaseModel):
    """Базовая модель для игнорирования лишних полей от API."""

    class ConfigDict:
        extra = "ignore"


class ContactInfo(BaseSchema):
    """Информация о контакте (телефон, email)."""

    type: str
    value: str


class FileInfo(BaseSchema):
    """Информация о прикрепленном файле."""

    id: str
    name: str | None = None
    extension: str | None = None
    size: int | None = None
    path: str | None = None


class Employee(BaseSchema):
    """Модель для сотрудника/исполнителя."""

    id: str
    name: str
    position: str | None = None


class Contractor(BaseSchema):
    """Модель для клиента/контрагента."""

    id: str
    # === ИЗМЕНЕНИЕ: Поля first_name и last_name теперь опциональны ===
    first_name: str | None = Field(default=None, alias="firstName")
    last_name: str | None = Field(default=None, alias="lastName")
    middle_name: str | None = Field(default=None, alias="middleName")
    contact_info: list[ContactInfo] = Field(alias="contactInfo", default_factory=list)

    @property
    def full_name(self) -> str:
        """
        Собирает полное имя для удобства.
        Теперь корректно обрабатывает None.
        """
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(part for part in parts if part)


class Money(BaseSchema):
    """Модель для денежных сумм."""

    value: float
    currency: str


class StateInfo(BaseSchema):
    """Информация о статусе сделки."""

    id: str
    name: str | None = None
    color: str | None = None


class ProgramInfo(BaseSchema):
    """Информация о программе/схеме сделки."""

    id: str
    name: str | None = None


class Deal(BaseSchema):
    """
    Основная модель, представляющая сделку из Мегаплана.
    Использует алиасы для маппинга длинных имен полей API на понятные имена.
    """

    id: str
    """Идентификатор сделки. Corresponds to JSON key: 'id'"""

    name: str
    """Название сделки. Corresponds to JSON key: 'name'"""

    number: str
    """Номер сделки (например, 5088-2025). Corresponds to JSON key: 'number'"""

    description: str | None = None
    """Описание сделки (HTML-текст). Corresponds to JSON key: 'description'"""

    price: Money | None = None
    """Цена сделки. Corresponds to JSON key: 'price'"""

    program: ProgramInfo
    """Программа/схема, по которой ведется сделка. Corresponds to JSON key: 'program'"""

    state: StateInfo
    """Текущий статус сделки. Corresponds to JSON key: 'state'"""

    contractor: Contractor | None = None
    """Клиент/контрагент по сделке. Corresponds to JSON key: 'contractor'"""

    attaches: list[FileInfo] = Field(default_factory=list)
    """Основные файлы, прикрепленные к сделке. Corresponds to JSON key: 'attaches'"""

    # --- Поля с алиасами для кастомных полей Мегаплана ---

    address: str | None = Field(
        default=None, alias="Category1000076CustomFieldPredmetRabotAdres"
    )
    """Адрес объекта работ. Corresponds to JSON key: 'Category1000076CustomFieldPredmetRabotAdres'"""

    cadastral_number: str | None = Field(
        default=None, alias="Category1000076CustomFieldPredmetRabotKadastroviyNomer"
    )
    """Кадастровый номер объекта. Corresponds to JSON key: 'Category1000076CustomFieldPredmetRabotKadastroviyNomer'"""

    visit_datetime: datetime | None = Field(
        default=None, alias="Category1000076CustomFieldViezdDataVremyaViezda"
    )
    """Дата и время выезда. Corresponds to JSON key: 'Category1000076CustomFieldViezdDataVremyaViezda'"""

    visit_result: str | None = Field(
        default=None, alias="Category1000076CustomFieldViezdRezultatViezda"
    )
    """Результат выезда (текстовое поле). Corresponds to JSON key: 'Category1000076CustomFieldViezdRezultatViezda'"""

    executors: list[Employee] = Field(
        alias="Category1000076CustomFieldViezdIspolnitel", default_factory=list
    )
    """Исполнители выезда. Corresponds to JSON key: 'Category1000076CustomFieldViezdIspolnitel'"""

    files_for_visit: list[FileInfo] = Field(
        alias="Category1000076CustomFieldViezdFayliDlyaViezda", default_factory=list
    )
    """Файлы для выезда. Corresponds to JSON key: 'Category1000076CustomFieldViezdFayliDlyaViezda'"""
    files_from_visit: list[FileInfo] = Field(
        alias="Category1000076CustomFieldViezdDokumentiIFotoSViezda", default_factory=list
    )
    """Файлы для выезда. Corresponds to JSON key: 'Category1000076CustomFieldViezdDokumentiIFotoSViezda'"""

    telegram_user_ids: list[str] = Field(
        alias="Category1000076CustomFieldSluzhebniyTelegramuserid", default_factory=list
    )
    """ID пользователей Telegram, привязанных к сделке. Corresponds to JSON key: 'Category1000076CustomFieldSluzhebniyTelegramuserid'"""

    # --- Валидаторы для преобразования данных ---

    @field_validator("visit_datetime", mode="before")
    @classmethod
    def extract_datetime_from_dict(cls, v):
        """Извлекает значение 'value' из объекта DateTime."""
        if isinstance(v, dict) and "value" in v:
            return v["value"]
        return v

    @field_validator("telegram_user_ids", mode="before")
    @classmethod
    def extract_ids_from_list(cls, v):
        """Извлекает только ID из списка объектов Employee."""
        if isinstance(v, list):
            return [item["id"] for item in v if isinstance(item, dict) and "id" in item]
        return v

    @field_validator("visit_datetime", mode="after")
    @classmethod
    def convert_to_local_timezone(cls, v: datetime | None):
        """
        Конвертирует datetime-объект в локальный часовой пояс приложения.
        Выполняется ПОСЛЕ основной валидации, когда `v` уже является объектом datetime.
        """
        # Если значение отсутствует, ничего не делаем
        if v is None:
            return None

        # Если объект уже имеет информацию о часовом поясе (а он будет иметь tzinfo=UTC),
        # то конвертируем его в наш локальный пояс.
        if v.tzinfo is not None:
            return v.astimezone(APP_TIMEZONE)

        # Запасной вариант: если бы дата пришла "наивной" (без tzinfo),
        # мы бы присвоили ей наш локальный часовой пояс.
        return v.replace(tzinfo=APP_TIMEZONE)


class DealCreationSchema(BaseModel):
    """
    Модель для пошагового сбора данных для создания новой сделки.
    Все поля опциональны, так как заполняются по очереди.
    """

    name: str | None = None
    description: str | None = None
    manager_id: int | None = None
    ticket_visit_datetime: datetime | None = None
    megaplan_user_id: int | None = None
    cadastral_to_visit: str | None = None
    address_to_visit: str | None = None

    # ПРИМЕР КАК ПОТОМ СОХРАНЯТЬ ДАННЫЕ С ЭТОЙ МОДЕЛЬЮ
    # Все данные собраны. Конвертируем Pydantic модель в словарь.
    # .model_dump(exclude_none=True) уберет все поля, которые мы не заполнили (остались None)
    # final_data_for_api = deal_draft.model_dump(exclude_none=True)

    # Передаем чистый словарь в метод клиента
    # created_deal = await crm_client.create_deal(**final_data_for_api)
