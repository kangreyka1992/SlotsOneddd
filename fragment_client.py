"""
Заглушка Fragment.
Реального API тут нет — это просто класс, чтобы бот запускался.
Когда настроишь TON-кошелёк и cookies Fragment — раскомментируй код интеграции.
"""

import logging

logging.basicConfig(level=logging.INFO)


class FragmentClient:
    def __init__(self, seed: str = None, cookies: dict = None):
        self.seed = seed
        self.cookies = cookies or {}
        self.enabled = bool(seed and all(cookies.values()))

    async def purchase_stars(self, username: str, stars: int):
        """Возвращает dict с tx_hash или None. Сейчас — заглушка."""
        if not self.enabled:
            raise Exception("Fragment не настроен")

        # РЕАЛЬНАЯ ИНТЕГРАЦИЯ (когда настроишь):
        #
        # from FragmentAPI import FragmentClient as RealFragment
        # client = RealFragment(seed=self.seed, cookies=self.cookies)
        # result = await client.purchase_stars(username, stars, payment_method="ton")
        # return {"tx_hash": getattr(result, "transaction_hash", None)}

        logging.warning(f"[FRAGMENT STUB] Вывод {stars} ⭐ на {username}")
        return {"tx_hash": None}


# Singleton
fragment_client = FragmentClient()