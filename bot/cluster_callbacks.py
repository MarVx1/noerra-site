# ============================================================
#  bot/cluster_callbacks.py — кнопки кластерного поста
#  (cluster_approve / cluster_confirm / cluster_reject)
#
#  Вынесено из bot/bot.py: этот блок самодостаточен (сам делает
#  локальные импорты adaptation.cluster/parsers.base) и не покрыт
#  тестами через bot.bot — перенос не затрагивает ни один из 47
#  тестов в tests/test_bot.py.
# ============================================================

from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.bot import dp, is_admin
from database.db import get_article_by_id, update_article_status, save_publication
from publisher.publisher import create_telegraph_page, send_to_channel


@dp.callback_query(F.data.startswith("cluster_approve:"))
async def on_cluster_approve(callback: CallbackQuery):
    """Первый шаг: запрос подтверждения перед публикацией кластера."""
    if not is_admin(callback.from_user.id):
        return

    ids = callback.data.split(":")[1]
    confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, опубликовать",
                callback_data=f"cluster_confirm:{ids}",
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"cluster_reject:{ids}",
            ),
        ],
    ])

    await callback.answer()
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n⚠️ Подтвердите публикацию кластера?",
            reply_markup=confirm_keyboard,
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("cluster_confirm:"))
async def on_cluster_confirm(callback: CallbackQuery):
    """Второй шаг: реальная публикация кластера после подтверждения."""
    if not is_admin(callback.from_user.id):
        return

    ids = [int(i) for i in callback.data.split(":")[1].split(",")]
    await callback.answer("Публикую...")

    from adaptation.cluster import build_cluster_post, build_telegraph_cluster
    from parsers.base import RawArticle
    from classifier.classifier import get_topic_ru

    # Собираем статьи
    articles_data = [get_article_by_id(aid) for aid in ids if get_article_by_id(aid)]
    if not articles_data:
        await callback.answer("Статьи не найдены")
        return

    topic = articles_data[0]["topic"]

    raw = [
        RawArticle(
            title=a["title"],
            url=a["url"] or "",
            abstract=a["abstract"] or "",
            source=a["source"],
        )
        for a in articles_data
    ]

    # Telegraph
    from database.db import get_youtube_by_topic
    yt_row = get_youtube_by_topic(topic)
    yt_article = None
    if yt_row:
        yt_article = RawArticle(
            title=yt_row["title"],
            url=yt_row["url"] or "",
            abstract=yt_row["abstract"] or "",
            source="youtube",
        )

    telegraph_content = build_telegraph_cluster(topic, raw, yt_article)
    topic_ru = get_topic_ru(topic)

    telegraph_url = await create_telegraph_page(
        title=f"Noerra: {topic_ru}",
        summary_ru=telegraph_content,
        source_url=articles_data[0]["url"] or "",
    )

    if not telegraph_url:
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ Ошибка Telegraph",
        )
        return

    # Финальный пост с реальным Telegraph URL
    final_post = build_cluster_post(
        topic=topic,
        articles=raw,
        youtube_article=yt_article,
        telegraph_url=telegraph_url,
    )

    msg_id = await send_to_channel(final_post)

    for aid in ids:
        update_article_status(aid, "published")
        save_publication(aid, telegraph_url, msg_id or 0)

    try:
        await callback.message.edit_text(
            callback.message.text + f"\n\n✅ Опубликовано → {telegraph_url}",
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("cluster_reject:"))
async def on_cluster_reject(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    ids = [int(i) for i in callback.data.split(":")[1].split(",")]
    for aid in ids:
        update_article_status(aid, "rejected")

    await callback.answer("Пропущено")
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ Пропущено",
        )
    except Exception:
        pass
