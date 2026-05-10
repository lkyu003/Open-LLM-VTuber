import asyncio
import json
import random
import re
from collections import deque
from typing import Awaitable, Callable, Deque, Optional, Set

import aiohttp
from loguru import logger


CHAT_WS_URLS = (
    "wss://kr-ss1.chat.naver.com/chat",
    "wss://kr-ss2.chat.naver.com/chat",
    "wss://kr-ss3.chat.naver.com/chat",
    "wss://kr-ss4.chat.naver.com/chat",
    "wss://kr-ss5.chat.naver.com/chat",
)
LIVE_DETAIL_URL = "https://api.chzzk.naver.com/service/v2/channels/{channel_id}/live-detail"
LIVE_STATUS_URL = "https://api.chzzk.naver.com/polling/v2/channels/{channel_id}/live-status"
ACCESS_TOKEN_URL = (
    "https://comm-api.game.naver.com/nng_main/v1/chats/access-token"
    "?channelId={chat_channel_id}&chatType=STREAMING"
)

CMD_PING = 0
CMD_PONG = 10000
CMD_CONNECTED = 10100
CMD_CHAT = 93101
CMD_RECENT_CHAT = 15101

EMOTICON_RE = re.compile(r":[A-Za-z0-9_]+:")
ONLY_REPEATED_REACTION_RE = re.compile(
    r"^[\u314b\u314e\u3160\u315c\u3161\s~!?.\u2026]+$"
)
ONLY_INITIALS_RE = re.compile(r"^[\u3131-\u314e\s~!?.\u2026]+$")


class ChzzkLiveChatSampler:
    """Sample readable CHZZK live chat messages and inject them as user input."""

    def __init__(
        self,
        channel_id: str,
        send_interval_sec: float,
        reconnect_interval_sec: float,
        recent_pool_size: int,
        min_message_length: int,
        max_message_length: int,
        ignore_while_conversation_active: bool,
        is_conversation_active: Callable[[], bool],
        inject_user_input: Callable[[str], Awaitable[None]],
    ) -> None:
        self.channel_id = channel_id
        self.send_interval_sec = max(send_interval_sec, 1.0)
        self.reconnect_interval_sec = max(reconnect_interval_sec, 3.0)
        self.recent_pool_size = max(recent_pool_size, 1)
        self.min_message_length = max(min_message_length, 1)
        self.max_message_length = max(max_message_length, self.min_message_length)
        self.ignore_while_conversation_active = ignore_while_conversation_active
        self.is_conversation_active = is_conversation_active
        self.inject_user_input = inject_user_input

        self._running = False
        self._recent_messages: Deque[str] = deque(maxlen=self.recent_pool_size)
        self._sent_messages: Set[str] = set()
        self._sent_message_order: Deque[str] = deque(maxlen=100)
        self._accepted_message_count = 0

    async def run(self) -> None:
        self._running = True
        logger.info(f"CHZZK live chat sampler enabled for channel {self.channel_id}")

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while self._running:
                try:
                    chat_info = await self._fetch_chat_channel_info(session)
                    if not chat_info:
                        await asyncio.sleep(self.reconnect_interval_sec)
                        continue
                    chat_channel_id, chat_ws_url = chat_info

                    access_token = await self._fetch_access_token(
                        session, chat_channel_id
                    )

                    await self._receive_chat(
                        session,
                        chat_channel_id,
                        chat_ws_url,
                        access_token or "",
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(
                        "CHZZK live chat sampler reconnecting after "
                        f"{type(e).__name__}: {e!r}"
                    )
                    logger.debug("CHZZK live chat sampler exception details", exc_info=e)
                    await asyncio.sleep(self.reconnect_interval_sec)

    def stop(self) -> None:
        self._running = False

    async def _fetch_chat_channel_info(
        self, session: aiohttp.ClientSession
    ) -> Optional[tuple[str, str]]:
        url = LIVE_STATUS_URL.format(channel_id=self.channel_id)
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning(f"CHZZK live-status returned HTTP {response.status}")
                return await self._fetch_chat_channel_info_from_live_detail(session)

            payload = await response.json()

        content = payload.get("content") or {}
        chat_channel_id = content.get("chatChannelId")

        if not chat_channel_id:
            logger.debug("CHZZK live chat unavailable from live-status")
            return await self._fetch_chat_channel_info_from_live_detail(session)

        return chat_channel_id, self._select_chat_ws_url(chat_channel_id)

    async def _fetch_chat_channel_info_from_live_detail(
        self, session: aiohttp.ClientSession
    ) -> Optional[tuple[str, str]]:
        url = LIVE_DETAIL_URL.format(channel_id=self.channel_id)
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning(f"CHZZK live-detail returned HTTP {response.status}")
                return None

            payload = await response.json()

        content = payload.get("content") or {}
        status = content.get("status")
        chat_active = content.get("chatActive", False)
        chat_channel_id = content.get("chatChannelId")

        if status != "OPEN" or not chat_active or not chat_channel_id:
            logger.debug(
                "CHZZK live chat unavailable "
                f"(status={status}, chat_active={chat_active})"
            )
            return None

        return chat_channel_id, self._select_chat_ws_url(chat_channel_id)

    def _select_chat_ws_url(self, chat_channel_id: str) -> str:
        server_index = sum(ord(char) for char in chat_channel_id) % len(CHAT_WS_URLS)
        return CHAT_WS_URLS[server_index]

    async def _fetch_access_token(
        self, session: aiohttp.ClientSession, chat_channel_id: str
    ) -> Optional[str]:
        url = ACCESS_TOKEN_URL.format(chat_channel_id=chat_channel_id)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://chzzk.naver.com",
            "Referer": f"https://chzzk.naver.com/live/{self.channel_id}/chat",
            "User-Agent": "Mozilla/5.0",
        }
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                logger.warning(f"CHZZK chat access-token returned HTTP {response.status}")
                return None

            payload = await response.json()

        content = payload.get("content") or {}
        return content.get("accessToken")

    async def _receive_chat(
        self,
        session: aiohttp.ClientSession,
        chat_channel_id: str,
        chat_ws_url: str,
        access_token: str,
    ) -> None:
        sampler_task = asyncio.create_task(self._sample_loop())
        try:
            async with session.ws_connect(
                chat_ws_url,
                heartbeat=20,
                headers={
                    "Origin": "https://chzzk.naver.com",
                    "User-Agent": "Mozilla/5.0",
                },
            ) as ws:
                await ws.send_json(
                    {
                        "ver": "2",
                        "cmd": 100,
                        "svcid": "game",
                        "cid": chat_channel_id,
                        "bdy": {
                            "uid": None,
                            "devType": 2001,
                            "accTkn": access_token,
                            "auth": "READ",
                        },
                        "tid": 1,
                    }
                )
                logger.info(
                    f"Connected to CHZZK live chat {chat_channel_id} via {chat_ws_url}"
                )

                async for message in ws:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_ws_payload(ws, message.data)
                    elif message.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
        finally:
            sampler_task.cancel()
            try:
                await sampler_task
            except asyncio.CancelledError:
                pass

    async def _handle_ws_payload(self, ws: aiohttp.ClientWebSocketResponse, data: str):
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return

        cmd = payload.get("cmd")
        if cmd == CMD_PING:
            await ws.send_json({"ver": "2", "cmd": CMD_PONG})
            return

        if cmd == CMD_CONNECTED:
            ret_code = payload.get("retCode")
            if ret_code != 0:
                raise RuntimeError(
                    "CHZZK live chat connect ACK failed "
                    f"(retCode={ret_code}, retMsg={payload.get('retMsg')})"
                )
            logger.debug("CHZZK live chat connect ACK succeeded")
            return

        if cmd not in (CMD_CHAT, CMD_RECENT_CHAT):
            return

        for raw_message in self._extract_messages(payload.get("bdy")):
            message = self._clean_message(raw_message)
            if message:
                self._recent_messages.append(message)
                self._accepted_message_count += 1
                if (
                    self._accepted_message_count == 1
                    or self._accepted_message_count % 50 == 0
                ):
                    logger.info(
                        "Buffered CHZZK live chat message "
                        f"#{self._accepted_message_count}: {message}"
                    )

    def _extract_messages(self, body) -> list[str]:
        if isinstance(body, list):
            return [
                item.get("msg") or item.get("content") or ""
                for item in body
                if isinstance(item, dict)
            ]

        if isinstance(body, dict):
            if isinstance(body.get("msg"), str):
                return [body["msg"]]
            if isinstance(body.get("content"), str):
                return [body["content"]]
            if isinstance(body.get("message"), str):
                return [body["message"]]

        return []

    def _clean_message(self, message: str) -> Optional[str]:
        text = EMOTICON_RE.sub("", message)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) < self.min_message_length or len(text) > self.max_message_length:
            return None

        if ONLY_REPEATED_REACTION_RE.fullmatch(text):
            return None

        if ONLY_INITIALS_RE.fullmatch(text) and len(set(text.replace(" ", ""))) <= 2:
            return None

        return text

    async def _sample_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.send_interval_sec)

            if (
                self.ignore_while_conversation_active
                and self.is_conversation_active()
            ):
                continue

            candidates = [
                message
                for message in self._recent_messages
                if message not in self._sent_messages
            ]
            if not candidates:
                continue

            message = random.choice(candidates)
            self._mark_message_sent(message)
            logger.info(f"Injecting CHZZK chat as user input: {message}")
            await self.inject_user_input(message)

    def _mark_message_sent(self, message: str) -> None:
        if len(self._sent_message_order) == self._sent_message_order.maxlen:
            oldest_message = self._sent_message_order.popleft()
            self._sent_messages.discard(oldest_message)

        self._sent_message_order.append(message)
        self._sent_messages.add(message)
