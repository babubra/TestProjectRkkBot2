import logging
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app_bot.crm_service.crm_client import CRMClient
from app_bot.database.models import Permission
from app_bot.filters.permission_filters import HasPermissionFilter
from app_bot.keyboards.add_files_keyboards import get_add_files_kb
from app_bot.keyboards.view_ticket_keyboards import DealActionCallback
from app_bot.utils.ui_utils import get_main_menu_message


add_files_router = Router()
logger = logging.getLogger(__name__)

# Максимальный размер файла в байтах (25 МБ)
MAX_FILE_SIZE = 25 * 1024 * 1024


class AddFilesFSM(StatesGroup):
    """FSM для процесса добавления файлов к сделке."""

    waiting_for_files = State()


# 1. Хендлер, запускающий процесс
@add_files_router.callback_query(
    DealActionCallback.filter(F.action == "add_files"),
    HasPermissionFilter(Permission.ADD_FILES_FROM_VISIT),
)
async def start_add_files(
    query: CallbackQuery, callback_data: DealActionCallback, state: FSMContext
):
    """Начинает процесс добавления файлов к сделке."""
    deal_id = callback_data.deal_id
    await state.set_state(AddFilesFSM.waiting_for_files)
    await state.update_data(deal_id=deal_id, uploaded_file_ids=[], pending_caption=None, name_counts={}, album_captions={})

    # Берем контекст из исходного сообщения
    message_lines = query.message.html_text.split("\n")
    deal_context = "\n".join(message_lines[:2])  # Первая строка: ссылка+дата, вторая: название

    await query.answer()
    await query.message.answer(
        f"📁 **Добавление файлов к сделке:**\n{deal_context}\n\n"
        "📸 Отправьте фото, видео или документы\n"
        "📎 Можно присылать по одному или сразу несколько (альбомом)\n\n"
        "✅ Когда закончите, нажмите кнопку ниже",
        reply_markup=get_add_files_kb(),
        disable_web_page_preview=True,  # Отключаем превью для ссылки на сделку
    )


# 2. Хендлер, принимающий файлы
@add_files_router.message(
    AddFilesFSM.waiting_for_files,
    F.content_type.in_({"photo", "document", "video"}),
    HasPermissionFilter(Permission.ADD_FILES_FROM_VISIT),
)
async def process_file(message: Message, state: FSMContext, bot: Bot, crm_client: CRMClient):
    """Ловит и обрабатывает один файл (фото, документ или видео)."""
    file_id = None
    file_name = "имя не определено"
    file_size = 0

    if message.photo:
        file_id = message.photo[-1].file_id
        file_size = message.photo[-1].file_size
        file_name = f"{file_id}.jpg"
    elif message.document:
        file_id = message.document.file_id
        file_size = message.document.file_size
        file_name = message.document.file_name
    elif message.video:
        file_id = message.video.file_id
        file_size = message.video.file_size
        file_name = message.video.file_name or f"{file_id}.mp4"

    # Выбор подписи для именования файла: приоритет
    # 1) caption у самого сообщения
    # 2) caption, сохранённый для альбома (media_group)
    # 3) отложенный текстовый caption (только для следующего файла, потом очищаем)
    data_tmp = await state.get_data()
    caption_source = None
    caption = None
    mg_id = getattr(message, "media_group_id", None)

    if message.caption:
        caption = message.caption
        caption_source = "message"
        # Если это альбом, запомним caption для остальных элементов альбома
        if mg_id:
            album_captions = data_tmp.get("album_captions", {})
            if mg_id not in album_captions:
                album_captions[mg_id] = caption
                await state.update_data(album_captions=album_captions)
    else:
        if mg_id:
            album_captions = data_tmp.get("album_captions", {})
            if mg_id in album_captions:
                caption = album_captions[mg_id]
                caption_source = "album"
        if not caption:
            pending = data_tmp.get("pending_caption")
            if pending:
                caption = pending
                caption_source = "pending"

    if caption:
        base = "_".join(caption.split())
        if message.photo:
            ext = ".jpg"
        elif message.document:
            orig = message.document.file_name or ""
            ext = orig[orig.rfind("."):] if "." in orig else ""
        elif message.video:
            orig = message.video.file_name or ""
            ext = orig[orig.rfind("."):] if orig and "." in orig else ".mp4"
        else:
            ext = ""
        # Обеспечиваем уникальность имени в рамках текущей сессии
        data_counts = await state.get_data()
        name_counts = data_counts.get("name_counts", {})
        key = f"{base}{ext}".lower()
        count = name_counts.get(key, 0) + 1
        name_counts[key] = count
        await state.update_data(name_counts=name_counts)
        file_name = f"{base}_{count}{ext}" if count > 1 else f"{base}{ext}"

        # Если caption пришёл отдельным текстовым сообщением — применяем только к одному следующему файлу
        if caption_source == "pending":
            await state.update_data(pending_caption=None)

    if not file_id:
        await message.answer("Не удалось получить информацию о файле.")
        return

    if file_size > MAX_FILE_SIZE:
        error_msg = (
            f"❌ <b>Файл «{file_name}» слишком большой</b> ({file_size / 1024 / 1024:.2f} МБ).\n"
            "Он не будет загружен. Лимит Telegram Bot API — 25 МБ. "
            "Пожалуйста, загрузите его вручную через веб-интерфейс Мегаплана."
        )
        await message.answer(error_msg)
        return

    status_msg = await message.answer(f"⏳ Загружаю «{file_name}»...")
    try:
        file_io = BytesIO()
        await bot.download(file_id, destination=file_io)
        file_bytes = file_io.getvalue()
    except Exception as e:
        logger.error(f"Ошибка скачивания файла {file_id} с серверов Telegram: {e}")
        await status_msg.edit_text(f"❌ Не удалось скачать «{file_name}» с серверов Telegram.")
        return

    try:
        uploaded_file_info = await crm_client.upload_file_from_bytes(
            file_content=file_bytes, file_name=file_name
        )
        if not uploaded_file_info or "id" not in uploaded_file_info:
            raise Exception("CRM не вернуло информацию о файле.")

        crm_file_id = uploaded_file_info["id"]

        data = await state.get_data()
        current_ids = data.get("uploaded_file_ids", [])
        current_ids.append(crm_file_id)
        await state.update_data(uploaded_file_ids=current_ids)

        await status_msg.edit_text(
            f"✅ Файл «{file_name}» успешно загружен.", reply_markup=get_add_files_kb()
        )

    except Exception as e:
        logger.error(f"Ошибка загрузки файла '{file_name}' в CRM: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Ошибка при загрузке «{file_name}» в CRM.")


# 2.1. Хендлер, принимающий текст как общий комментарий к файлам
@add_files_router.message(
    AddFilesFSM.waiting_for_files,
    F.text,
    HasPermissionFilter(Permission.ADD_FILES_FROM_VISIT),
)
async def set_pending_caption(message: Message, state: FSMContext):
    """Сохраняет текст как комментарий для именования следующих файлов."""
    text = (message.text or "").strip()
    if not text:
        await state.update_data(pending_caption=None)
        await message.answer("Комментарий для файлов очищен.")
        return
    await state.update_data(pending_caption=text)
    await message.answer("Комментарий сохранён. Он будет использоваться для имен файлов.")

# 3. Хендлер, завершающий процесс
@add_files_router.callback_query(
    F.data == "add_files_complete",
    AddFilesFSM.waiting_for_files,
    HasPermissionFilter(Permission.ADD_FILES_FROM_VISIT),
)
async def complete_add_files(
    query: CallbackQuery, state: FSMContext, crm_client: CRMClient, session: AsyncSession
):
    """Завершает процесс и прикрепляет все загруженные файлы к сделке."""
    await query.answer()
    data = await state.get_data()
    deal_id = data.get("deal_id")
    uploaded_file_ids = data.get("uploaded_file_ids", [])

    if not uploaded_file_ids:
        # Редактируем сообщение, на котором была нажата кнопка
        await query.message.edit_text("Вы не загрузили ни одного файла. Операция отменена.")
        await state.clear()
        return

    status_msg = await query.message.edit_text(
        f"⏳ Прикрепляю {len(uploaded_file_ids)} файлов к сделке ID: {deal_id}..."
    )

    try:
        success = await crm_client.attach_files_to_deal_visit_docs(
            deal_id=deal_id, file_ids=uploaded_file_ids
        )
        if success:
            await status_msg.edit_text(
                f"✅ Успешно! {len(uploaded_file_ids)} файлов добавлено к сделке."
            )
            await get_main_menu_message(
                message=query.message, session=session, crm_client=crm_client
            )
        else:
            await status_msg.edit_text("❌ Произошла ошибка при прикреплении файлов к сделке.")
    except Exception as e:
        logger.error(
            f"Критическая ошибка при прикреплении файлов к сделке {deal_id}: {e}", exc_info=True
        )
        await status_msg.edit_text(
            "❌ Произошла критическая ошибка. Свяжитесь с администратором."
        )
        await get_main_menu_message(
            message=query.message, session=session, crm_client=crm_client
        )
    finally:
        await state.clear()


# 4. Хендлер отмены
@add_files_router.callback_query(F.data == "add_files_cancel", AddFilesFSM.waiting_for_files)
async def cancel_add_files(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, crm_client: CRMClient
):
    """Отменяет процесс добавления файлов и возвращает в главное меню."""
    await state.clear()
    await query.answer("Операция отменена.")
    # Удаляем сообщение с кнопками, чтобы очистить чат
    await query.message.delete()
    await get_main_menu_message(message=query.message, session=session, crm_client=crm_client)
