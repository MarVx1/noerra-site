# ============================================================
#  bot/callbacks.py — кнопки одиночной модерации и дайджеста
#  (approve/reject, draft_*, digest_*)
#
#  Вынесено из bot/bot.py. Патчится тестами напрямую (tests/test_bot.py
#  импортирует этот модуль как `cb_mod`) — если добавляешь новый вызов
#  внешней зависимости внутри этих обработчиков, импортируй её сюда же,
#  а не через bot.bot/bot.publishing: иначе patch.object(cb_mod, "...")
#  перестанет перехватывать (поиск имени идёт по __globals__ функции,
#  т.е. по namespace модуля, где эта функция ОПРЕДЕЛЕНА).
# ============================================================

import logging
import re

from aiogram import F
from aiogram.types import CallbackQuery

from bot.bot import dp, is_admin
from bot.publishing import _publish_article, send_for_moderation
from bot.keyboards import draft_publish_keyboard
from database.db import update_article_status, get_draft_by_id, get_article_by_id, save_editor_feedback

logger = logging.getLogger(__name__)

# TELEGRAPH_URL — плейсхолдер в summaries.post_text (см. scheduler.py):
# реальный URL появляется только в момент публикации, когда создаётся
# страница Telegraph. Для предпросмотра подставляем нейтральную пометку
# вместо рабочей ссылки — вёрстка (эмодзи, 👇, разбивка на абзацы)
# при этом остаётся точно такой же, как в реальном посте.
_TELEGRAPH_PLACEHOLDER_RE = re.compile(
    r"<a href=['\"]TELEGRAPH_URL['\"]>(.*?)</a>", re.DOTALL,
)


def _preview_post_text(post_text: str) -> str:
    """Финальный пост с плейсхолдером ссылки вместо TELEGRAPH_URL —
    для предпросмотра редактору после одобрения (см. on_draft_approve)."""
    return _TELEGRAPH_PLACEHOLDER_RE.sub(
        r"\1 (ссылка появится при публикации)", post_text,
    )


# ── Кнопки одиночной модерации ────────────────────────────────

@dp.callback_query(F.data.startswith("approve:"))
async def on_approve(callback: CallbackQuery):
    logger.info(f"✅ on_approve callback: data={callback.data}, user={callback.from_user.id}")
    if not is_admin(callback.from_user.id):
        logger.warning(f"Unauthorized user {callback.from_user.id} tried to approve")
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    article_id = int(callback.data.split(":")[1])
    logger.info(f"Approving article_id={article_id}")
    await callback.answer("Публикую...", show_alert=False)
    ok, result = await _publish_article(article_id)
    suffix = f"\n\n✅ Опубликовано → {result}" if ok else f"\n\n❌ Ошибка: {result}"
    try:
        await callback.message.edit_text(
            callback.message.text + suffix,
        )
        logger.info(f"Article {article_id} published successfully: {result}")
    except Exception as e:
        logger.error(f"Failed to edit message after approve: {e}")
        pass


@dp.callback_query(F.data.startswith("reject:"))
async def on_reject(callback: CallbackQuery):
    logger.info(f"❌ on_reject callback: data={callback.data}, user={callback.from_user.id}")
    if not is_admin(callback.from_user.id):
        logger.warning(f"Unauthorized user {callback.from_user.id} tried to reject")
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    article_id = int(callback.data.split(":")[1])
    logger.info(f"Rejecting article_id={article_id}")
    update_article_status(article_id, "rejected")
    await callback.answer("Отклонено", show_alert=False)
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ Отклонено",
        )
        logger.info(f"Article {article_id} rejected")
    except Exception as e:
        logger.error(f"Failed to edit message after reject: {e}")
        pass


@dp.callback_query(F.data.startswith("draft_approve:"))
async def on_draft_approve(callback: CallbackQuery):
    logger.info(f"📝 on_draft_approve callback: data={callback.data}, user={callback.from_user.id}")
    if not is_admin(callback.from_user.id):
        logger.warning(f"Unauthorized user {callback.from_user.id} tried to draft_approve")
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    draft_id = int(callback.data.split(":")[1])
    logger.info(f"Approving draft_id={draft_id}")
    draft = get_draft_by_id(draft_id)
    if not draft:
        logger.error(f"Draft {draft_id} not found")
        await callback.answer("Драфт не найден", show_alert=True)
        return

    save_editor_feedback(draft_id, str(callback.from_user.id), "approved", reason="approved by editor")
    if draft["article_id"]:
        update_article_status(draft["article_id"], "approved")

    keyboard = draft_publish_keyboard(draft_id)
    await callback.answer("Одобрено! Теперь можно опубликовать.", show_alert=False)

    # ВАЖНО: не используем parse_mode="HTML" на ЭТОЙ карточке —
    # callback.message.text это уже plain text (с literal <b>, </b>,
    # <a href='...'> из &lt;b&gt; и т.д.), а parse_mode="HTML" заставит
    # Telegram попытаться распарсить эти символы как HTML-теги, что
    # вызовет "Unexpected end tag". Кнопку публикации переносим на новое
    # сообщение с реальным предпросмотром (ниже) — здесь просто отмечаем
    # карточку модерации как одобренную.
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ Одобрено — предпросмотр финального поста ниже.",
        )
    except Exception as e:
        logger.error(f"Failed to edit message after draft_approve: {e}")

    # Реальный текст поста, который получит подписчик — тот же
    # summaries.post_text, что уходит в канал при публикации (см.
    # scheduler.py), с плейсхолдером вместо ссылки на Telegraph (она
    # создаётся только в момент публикации). Отдельное НОВОЕ сообщение
    # с parse_mode="HTML", чтобы вёрстка отрендерилась точно как в канале.
    article = get_article_by_id(draft["article_id"]) if draft["article_id"] else None
    post_text = (article["post_text"] if article else "") or ""
    if post_text:
        try:
            await callback.message.answer(
                f"👁 <b>Предпросмотр финального поста:</b>\n\n{_preview_post_text(post_text)}",
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            logger.info(f"Draft {draft_id} approved, post preview sent with publish button")
        except Exception as e:
            logger.error(f"Failed to send post preview for draft {draft_id}: {e}")
    else:
        # Нет post_text (article_id=0 или ещё не сгенерирован summary) —
        # кнопку показываем хотя бы на старой карточке, чтобы публикация
        # оставалась доступна.
        logger.warning(f"Draft {draft_id}: no post_text for preview, falling back to inline button")
        try:
            await callback.message.answer(
                "⚠️ Предпросмотр недоступен (нет сохранённого текста поста).",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"Failed to send fallback publish button for draft {draft_id}: {e}")


@dp.callback_query(F.data.startswith("draft_reject:"))
async def on_draft_reject(callback: CallbackQuery):
    logger.info(f"📝 on_draft_reject callback: data={callback.data}, user={callback.from_user.id}")
    if not is_admin(callback.from_user.id):
        logger.warning(f"Unauthorized user {callback.from_user.id} tried to draft_reject")
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    parts = callback.data.split(":")
    draft_id = int(parts[1])
    reason = parts[2] if len(parts) > 2 else "rejected by editor"
    logger.info(f"Rejecting draft_id={draft_id}, reason={reason}")
    draft = get_draft_by_id(draft_id)
    if not draft:
        logger.error(f"Draft {draft_id} not found")
        await callback.answer("Драфт не найден", show_alert=True)
        return

    save_editor_feedback(draft_id, str(callback.from_user.id), "rejected", reason=reason)
    if draft["article_id"]:
        update_article_status(draft["article_id"], "rejected")

    await callback.answer("Отклонено", show_alert=False)
    try:
        await callback.message.edit_text(
            callback.message.text + f"\n\n❌ Отклонено ({reason})",
        )
        logger.info(f"Draft {draft_id} rejected: {reason}")
    except Exception as e:
        logger.error(f"Failed to edit message after draft_reject: {e}")
        pass


@dp.callback_query(F.data.startswith("draft_edit:"))
async def on_draft_edit(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    draft_id = int(callback.data.split(":")[1])
    draft = get_draft_by_id(draft_id)
    if not draft:
        await callback.answer("Драфт не найден")
        return

    save_editor_feedback(draft_id, str(callback.from_user.id), "edit_requested", reason="editor requested edits")
    if draft["article_id"]:
        update_article_status(draft["article_id"], "edit_requested")

    await callback.answer("Редактирование запрошено")
    keyboard = draft_publish_keyboard(draft_id)
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n✏️ Редактирование запрошено\n\nПосле редакции нажмите «Опубликовать в канал».",
            reply_markup=keyboard,
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("draft_publish:"))
async def on_draft_publish(callback: CallbackQuery):
    """Публикует одобренный драфт в канал: Telegraph → Telegram."""
    logger.info(f"📤 on_draft_publish callback: data={callback.data}, user={callback.from_user.id}")
    if not is_admin(callback.from_user.id):
        logger.warning(f"Unauthorized user {callback.from_user.id} tried to draft_publish")
        await callback.answer("❌ Нет прав", show_alert=True)
        return

    draft_id = int(callback.data.split(":")[1])
    logger.info(f"Publishing draft_id={draft_id}")
    draft = get_draft_by_id(draft_id)
    if not draft:
        logger.error(f"Draft {draft_id} not found")
        await callback.answer("Драфт не найден", show_alert=True)
        return

    article_id = draft["article_id"]
    if not article_id:
        await callback.answer("❌ Нет статьи для публикации", show_alert=True)
        return

    await callback.answer("Публикую в канал...", show_alert=False)

    # Публикуем через _publish_article (Telegraph + канал)
    ok, result = await _publish_article(article_id)

    if ok:
        try:
            await callback.message.edit_text(
                callback.message.text + f"\n\n📤 Опубликовано в канал\n🔗 {result}",
            )
            logger.info(f"Draft {draft_id} published to channel: {result}")
        except Exception as e:
            logger.error(f"Failed to edit message after publish: {e}")
    else:
        try:
            await callback.message.edit_text(
                callback.message.text + f"\n\n❌ Ошибка публикации: {result}",
            )
        except Exception:
            pass
        logger.error(f"Draft {draft_id} publish failed: {result}")


# ── Кнопки дайджеста ─────────────────────────────────────────

@dp.callback_query(F.data.startswith("digest_approve:"))
async def on_digest_approve(callback: CallbackQuery):
    """Публикует все статьи из дайджеста."""
    if not is_admin(callback.from_user.id):
        return
    ids = [int(i) for i in callback.data.split(":")[1].split(",")]
    await callback.answer(f"Публикую {len(ids)} статей...")
    await callback.message.edit_text(
        callback.message.text + f"\n\n⏳ Публикую {len(ids)} статей...",
    )

    ok_count = 0
    for article_id in ids:
        ok, _ = await _publish_article(article_id)
        if ok:
            ok_count += 1

    try:
        await callback.message.edit_text(
            callback.message.text.replace(f"⏳ Публикую {len(ids)} статей...", "") +
            f"\n\n✅ Опубликовано: {ok_count} из {len(ids)}",
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("digest_one_by_one:"))
async def on_digest_one_by_one(callback: CallbackQuery):
    """Отправляет статьи по одной для индивидуальной модерации."""
    if not is_admin(callback.from_user.id):
        return
    ids = [int(i) for i in callback.data.split(":")[1].split(",")]
    await callback.answer("Отправляю по одной...")
    await callback.message.edit_text(
        callback.message.text + f"\n\n📋 Отправляю {len(ids)} статей по одной...",
    )
    for article_id in ids:
        await send_for_moderation(article_id)


@dp.callback_query(F.data == "digest_reject_all")
async def on_digest_reject_all(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("Пропущено")
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ Дайджест пропущен",
        )
    except Exception:
        pass
