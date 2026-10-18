from aiogram.filters import BaseFilter


class IsAdmin(BaseFilter):
    """Sirf ADMIN_IDS (environment variable) mein likhe numeric IDs pass hote hain."""

    async def __call__(self, event, config) -> bool:
        u = getattr(event, "from_user", None)
        return u is not None and u.id in config.admin_ids
