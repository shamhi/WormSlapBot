import asyncio
from time import time
from random import randint
from datetime import datetime
from urllib.parse import unquote

import aiohttp
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered
from pyrogram.raw.functions.messages import RequestWebView

from bot.config import settings
from bot.utils import logger
from bot.utils.boosts import FreeBoosts, UpgradableBoosts
from bot.exceptions import InvalidSession
from .headers import headers


class Slapper:
    def __init__(self, tg_client: Client):
        self.session_name = tg_client.name
        self.tg_client = tg_client

    async def get_tg_web_data(self, proxy: str | None) -> str:
        try:
            if proxy:
                proxy = Proxy.from_str(proxy)
                proxy_dict = dict(
                    scheme=proxy.protocol,
                    hostname=proxy.host,
                    port=proxy.port,
                    username=proxy.login,
                    password=proxy.password
                )
            else:
                proxy_dict = None

            self.tg_client.proxy = proxy_dict

            if not self.tg_client.is_connected:
                try:
                    await self.tg_client.connect()
                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)

            web_view = await self.tg_client.invoke(RequestWebView(
                peer=await self.tg_client.resolve_peer('wormfare_slap_bot'),
                bot=await self.tg_client.resolve_peer('wormfare_slap_bot'),
                platform='android',
                from_bot_menu=False,
                url='https://www.clicker.wormfare.com/'
            ))

            auth_url = web_view.url
            tg_web_data = unquote(
                string=unquote(
                    string=auth_url.split('tgWebAppData=', maxsplit=1)[1].split('&tgWebAppVersion', maxsplit=1)[0]))

            if self.tg_client.is_connected:
                await self.tg_client.disconnect()

            return tg_web_data

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error during Authorization: {error}")
            await asyncio.sleep(delay=7)

    async def login(self, http_client: aiohttp.ClientSession, tg_web_data: str) -> str:
        try:
            response = await http_client.post(
                url='https://api.clicker.wormfare.com/auth/login',
                json={"initData": tg_web_data})
            response.raise_for_status()

            response_json = await response.json()
            access_token = response_json['accessToken']

            return access_token
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error while getting Access Token: {error}")
            await asyncio.sleep(delay=7)

    async def get_profile_data(self, http_client: aiohttp.ClientSession) -> dict[str]:
        try:
            response = await http_client.get(
                url='https://api.clicker.wormfare.com/user/profile',
                json={})
            response.raise_for_status()

            response_json = await response.json()
            profile_data = response_json

            return profile_data
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error while getting Profile Data: {error}")
            await asyncio.sleep(delay=7)

    async def apply_boost(self, http_client: aiohttp.ClientSession, boost_type: FreeBoosts) -> bool:
        try:
            response = await http_client.post(
                url='https://api.clicker.wormfare.com/game/activate-daily-boost',
                json={'type': boost_type})
            response.raise_for_status()

            return True
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when Apply {boost_type} Boost: {error}")
            await asyncio.sleep(delay=7)

            return False

    async def upgrade_boost(self, http_client: aiohttp.ClientSession, boost_type: UpgradableBoosts) -> bool:
        try:
            response = await http_client.post(
                url='https://api.clicker.wormfare.com/game/buy-boost',
                json={'type': boost_type})
            response.raise_for_status()

            return True
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when Upgrade {boost_type} Boost: {error}")
            await asyncio.sleep(delay=7)

            return False

    async def get_daily_boosts(self, http_client: aiohttp.ClientSession) -> tuple[int, int]:
        try:
            response = await http_client.get(
                url='https://api.clicker.wormfare.com/game/daily-boosts',
                json={})
            response.raise_for_status()

            response_json = await response.json()

            turbo_count = response_json[1]['availableCount']
            energy_count = response_json[0]['availableCount']

            return turbo_count, energy_count
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when getting Daily Boosts: {error}")
            await asyncio.sleep(delay=7)

            return 0, 0

    async def get_upgradable_boosts(self, http_client: aiohttp.ClientSession) -> list[dict[str]]:
        try:
            response = await http_client.get(
                url='https://api.clicker.wormfare.com/game/available-boosts',
                json={})
            response.raise_for_status()

            response_json = await response.json()
            upgradable_boosts = response_json

            return upgradable_boosts
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when getting Upgradable Boosts: {error}")
            await asyncio.sleep(delay=7)

    async def send_slaps(self, http_client: aiohttp.ClientSession, slaps: int, active_turbo: bool) -> dict[str]:
        try:
            timestamp = (round(datetime.timestamp(datetime.now()), 3) - 10) * 1000
            response = await http_client.post(
                url='https://api.clicker.wormfare.com/game/save-clicks',
                json={'amount': slaps, 'isTurbo': active_turbo, 'startTimestamp': timestamp})
            response.raise_for_status()

            response_json = await response.json()
            player_data = response_json

            return player_data
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when Slapping: {error}")
            await asyncio.sleep(delay=7)

    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
            ip = (await response.json()).get('origin')
            logger.info(f"{self.session_name} | Proxy IP: {ip}")
        except Exception as error:
            logger.error(f"{self.session_name} | Proxy: {proxy} | Error: {error}")

    async def run(self, proxy: str | None) -> None:
        access_token_created_time = 0
        active_turbo = False

        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None

        async with aiohttp.ClientSession(headers=headers, connector=proxy_conn) as http_client:
            if proxy:
                await self.check_proxy(http_client=http_client, proxy=proxy)

            while True:
                try:
                    if time() - access_token_created_time >= 3600:
                        tg_web_data = await self.get_tg_web_data(proxy=proxy)
                        access_token = await self.login(http_client=http_client, tg_web_data=tg_web_data)

                        http_client.headers["Authorization"] = f"Bearer {access_token}"
                        headers["Authorization"] = f"Bearer {access_token}"

                        access_token_created_time = time()

                        profile_data = await self.get_profile_data(http_client=http_client)

                        balance = profile_data['score']

                        slap_level = profile_data['energyPerTap']

                        earned_for_today = profile_data['earnedScoreToday']
                        earned_for_week = profile_data['earnedScoreThisWeek']

                        rank = profile_data['rank']

                        logger.info(f"{self.session_name} | Balance: <c>{balance}</c> | Rank: <m>{rank}</m>")

                        logger.info(f"{self.session_name} | Earned today: <g>+{earned_for_today}</g>")
                        logger.info(f"{self.session_name} | Earned week: <g>+{earned_for_week}</g>")

                    slaps = randint(a=settings.RANDOM_SLAPS_COUNT[0], b=settings.RANDOM_SLAPS_COUNT[1])

                    if active_turbo:
                        slaps += settings.ADD_SLAPS_ON_TURBO

                    slaps *= slap_level

                    player_data = await self.send_slaps(http_client=http_client, slaps=slaps, active_turbo=active_turbo)

                    if not player_data:
                        continue

                    available_energy = player_data['energyLeft']
                    new_balance = player_data['score']
                    calc_slaps = new_balance - balance
                    balance = new_balance
                    total = player_data['totalEarnedScore']
                    slap_level = profile_data['energyPerTap']

                    daily_turbo_count, daily_energy_count = await self.get_daily_boosts(http_client=http_client)

                    upgradable_boosts = await self.get_upgradable_boosts(http_client=http_client)

                    next_slap_price = upgradable_boosts[2]['priceInScore']
                    next_slap_level = upgradable_boosts[2]['level']
                    next_energy_level = upgradable_boosts[0]['level']
                    next_energy_price = upgradable_boosts[0]['priceInScore']
                    next_charge_level = upgradable_boosts[1]['level']
                    next_charge_price = upgradable_boosts[1]['priceInScore']

                    logger.success(f"{self.session_name} | Successful slapped! | "
                                   f"Balance: <c>{balance}</c> (<g>+{calc_slaps}</g>) | Total: <e>{total}</e>")

                    if active_turbo is False:
                        if (daily_energy_count > 0
                                and available_energy < settings.MIN_AVAILABLE_ENERGY
                                and settings.APPLY_DAILY_ENERGY is True):
                            logger.info(f"{self.session_name} | Sleep 5s before activating the daily energy boost")
                            await asyncio.sleep(delay=5)

                            status = await self.apply_boost(http_client=http_client, boost_type=FreeBoosts.ENERGY)
                            if status is True:
                                logger.success(f"{self.session_name} | Energy boost applied")

                                await asyncio.sleep(delay=5)

                            continue

                        if daily_turbo_count > 0 and settings.APPLY_DAILY_TURBO is True:
                            logger.info(f"{self.session_name} | Sleep 5s before activating the daily turbo boost")
                            await asyncio.sleep(delay=5)

                            status = await self.apply_boost(http_client=http_client, boost_type=FreeBoosts.TURBO)
                            if status is True:
                                logger.success(f"{self.session_name} | Turbo boost applied")

                                await asyncio.sleep(delay=5)

                                active_turbo = True

                            continue

                        if (settings.AUTO_UPGRADE_SLAP is True
                                and balance > next_slap_price
                                and next_slap_level <= settings.MAX_SLAP_LEVEL):
                            logger.info(f"{self.session_name} | Sleep 5s before upgrade slap to {next_slap_level} lvl")
                            await asyncio.sleep(delay=5)

                            status = await self.upgrade_boost(http_client=http_client,
                                                              boost_type=UpgradableBoosts.SLAP)
                            if status is True:
                                logger.success(f"{self.session_name} | Slap upgraded to {next_slap_level} lvl")

                                await asyncio.sleep(delay=5)

                            continue

                        if (settings.AUTO_UPGRADE_ENERGY is True
                                and balance > next_energy_price
                                and next_energy_level <= settings.MAX_ENERGY_LEVEL):
                            logger.info(
                                f"{self.session_name} | Sleep 5s before upgrade energy to {next_energy_level} lvl")
                            await asyncio.sleep(delay=5)

                            status = await self.upgrade_boost(http_client=http_client,
                                                              boost_type=UpgradableBoosts.ENERGY)
                            if status is True:
                                logger.success(f"{self.session_name} | Energy upgraded to {next_energy_level} lvl")

                                await asyncio.sleep(delay=5)

                            continue

                        if (settings.AUTO_UPGRADE_CHARGE is True
                                and balance > next_charge_price
                                and next_charge_level <= settings.MAX_CHARGE_LEVEL):
                            logger.info(
                                f"{self.session_name} | Sleep 5s before upgrade charge to {next_charge_level} lvl")
                            await asyncio.sleep(delay=5)

                            status = await self.upgrade_boost(http_client=http_client,
                                                              boost_type=UpgradableBoosts.CHARGE)
                            if status is True:
                                logger.success(f"{self.session_name} | Charge upgraded to {next_charge_level} lvl")

                                await asyncio.sleep(delay=5)

                            continue

                        if available_energy < settings.MIN_AVAILABLE_ENERGY:
                            logger.info(f"{self.session_name} | Minimum energy reached: {available_energy}")
                            logger.info(f"{self.session_name} | Sleep {settings.SLEEP_BY_MIN_ENERGY}s")

                            await asyncio.sleep(delay=settings.SLEEP_BY_MIN_ENERGY)

                            continue

                except InvalidSession as error:
                    raise error

                except Exception as error:
                    logger.error(f"{self.session_name} | Unknown error: {error}")
                    await asyncio.sleep(delay=7)

                else:
                    sleep_between_clicks = randint(a=settings.SLEEP_BETWEEN_SLAP[0], b=settings.SLEEP_BETWEEN_SLAP[1])

                    if active_turbo is True:
                        active_turbo = False

                    logger.info(f"Sleep {sleep_between_clicks}s")
                    await asyncio.sleep(delay=sleep_between_clicks)


async def run_slapper(tg_client: Client, proxy: str | None):
    try:
        await Slapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
