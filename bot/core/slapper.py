import asyncio
from time import time
from random import randint
from datetime import datetime
from urllib.parse import unquote

import aiohttp
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.types import User
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered
from pyrogram.raw.functions.messages import RequestWebView
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import settings
from bot.utils import logger
from bot.utils.boosts import FreeBoosts, UpgradableBoosts
from bot.exceptions import InvalidSession
from db.functions import get_user_proxy, get_user_agent, save_log
from .headers import headers


local_db = {}


class Slapper:
    def __init__(self, tg_client: Client, db_pool: async_sessionmaker, user_data: User):
        self.session_name = tg_client.name
        self.tg_client = tg_client
        self.db_pool = db_pool
        self.user_data = user_data

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
                url='https://elcevb3oz4.execute-api.eu-central-1.amazonaws.com/auth/login',
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
                url='https://elcevb3oz4.execute-api.eu-central-1.amazonaws.com/user/profile',
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
                url='https://elcevb3oz4.execute-api.eu-central-1.amazonaws.com/game/activate-daily-boost',
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
                url='https://elcevb3oz4.execute-api.eu-central-1.amazonaws.com/game/buy-boost',
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
                url='https://elcevb3oz4.execute-api.eu-central-1.amazonaws.com/game/daily-boosts',
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
                url='https://elcevb3oz4.execute-api.eu-central-1.amazonaws.com/game/available-boosts',
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
                url='https://elcevb3oz4.execute-api.eu-central-1.amazonaws.com/game/save-clicks',
                json={'amount': slaps, 'isTurbo': active_turbo, 'startTimestamp': timestamp})
            response.raise_for_status()

            response_json = await response.json()
            player_data = response_json

            return player_data
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when Slapping: {error}")
            await asyncio.sleep(delay=7)

    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> bool:
        try:
            response = await http_client.get(url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
            ip = (await response.json()).get('origin')
            logger.info(f"{self.session_name} | Proxy IP: {ip}")

            return bool(ip)
        except Exception as error:
            logger.error(f"{self.session_name} | Proxy: {proxy} | Error: {error}")

            return False

    async def run(self, proxy: str | None) -> None:
        active_turbo = False

        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None

        user_agent = await get_user_agent(db_pool=self.db_pool, phone_number=self.user_data.phone_number)
        headers['User-Agent'] = user_agent

        async with aiohttp.ClientSession(headers=headers, connector=proxy_conn) as http_client:
            if proxy:
                status = await self.check_proxy(http_client=http_client, proxy=proxy)
                if status is not True:
                    return

            while True:
                try:
                    local_token = local_db[self.session_name]['Token']
                    if not local_token:
                        tg_web_data = await self.get_tg_web_data(proxy=proxy)
                        access_token = await self.login(http_client=http_client, tg_web_data=tg_web_data)

                        http_client.headers["Authorization"] = f"Bearer {access_token}"
                        headers["Authorization"] = f"Bearer {access_token}"

                        local_db[self.session_name]['Token'] = access_token

                        profile_data = await self.get_profile_data(http_client=http_client)

                        balance = profile_data['score']

                        slap_level = profile_data['energyPerTap']

                        local_db[self.session_name]['Balance'] = balance
                        local_db[self.session_name]['SlapLevel'] = slap_level

                        earned_for_today = profile_data['earnedScoreToday']
                        earned_for_week = profile_data['earnedScoreThisWeek']

                        rank = profile_data['rank']

                        logger.info(f"{self.session_name} | Balance: <c>{balance}</c> | Rank: <m>{rank}</m>")

                        logger.info(f"{self.session_name} | Earned today: <g>+{earned_for_today}</g>")
                        logger.info(f"{self.session_name} | Earned week: <g>+{earned_for_week}</g>")
                    else:
                        http_client.headers["Authorization"] = f"Bearer {local_token}"

                        balance = local_db[self.session_name]['Balance']
                        slap_level = local_db[self.session_name]['SlapLevel']

                    slaps = randint(a=settings.RANDOM_SLAPS_COUNT[0], b=settings.RANDOM_SLAPS_COUNT[1])

                    if active_turbo:
                        slaps += settings.ADD_SLAPS_ON_TURBO

                    slaps *= slap_level

                    player_data = await self.send_slaps(http_client=http_client, slaps=slaps, active_turbo=active_turbo)

                    if not player_data:
                        await save_log(
                            db_pool=self.db_pool,
                            phone=self.user_data.phone_number,
                            status="ERROR",
                            amount=balance,
                        )
                        continue

                    available_energy = player_data['energyLeft']
                    new_balance = player_data['score']
                    calc_slaps = new_balance - balance
                    balance = new_balance
                    total = player_data['totalEarnedScore']

                    local_db[self.session_name]['Balance'] = balance

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

                    await save_log(
                        db_pool=self.db_pool,
                        phone=self.user_data.phone_number,
                        status="SLAP",
                        amount=balance,
                    )

                    if active_turbo is False:
                        if (daily_energy_count > 0
                                and available_energy < settings.MIN_AVAILABLE_ENERGY
                                and settings.APPLY_DAILY_ENERGY is True):
                            logger.info(f"{self.session_name} | Sleep 5s before activating the daily energy boost")
                            await asyncio.sleep(delay=5)

                            status = await self.apply_boost(http_client=http_client, boost_type=FreeBoosts.ENERGY)
                            if status is True:
                                logger.success(f"{self.session_name} | Energy boost applied")

                                await save_log(
                                    db_pool=self.db_pool,
                                    phone=self.user_data.phone_number,
                                    status="APPLY ENERGY BOOST",
                                    amount=balance,
                                )

                                await asyncio.sleep(delay=5)

                                continue

                        if daily_turbo_count > 0 and settings.APPLY_DAILY_TURBO is True:
                            logger.info(f"{self.session_name} | Sleep 5s before activating the daily turbo boost")
                            await asyncio.sleep(delay=5)

                            status = await self.apply_boost(http_client=http_client, boost_type=FreeBoosts.TURBO)
                            if status is True:
                                logger.success(f"{self.session_name} | Turbo boost applied")

                                await save_log(
                                    db_pool=self.db_pool,
                                    phone=self.user_data.phone_number,
                                    status="APPLY TURBO BOOST",
                                    amount=balance,
                                )

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

                                await save_log(
                                    db_pool=self.db_pool,
                                    phone=self.user_data.phone_number,
                                    status="UPGRADE SLAP",
                                    amount=balance,
                                )

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

                                await save_log(
                                    db_pool=self.db_pool,
                                    phone=self.user_data.phone_number,
                                    status="UPGRADE ENERGY",
                                    amount=balance,
                                )

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

                                await save_log(
                                    db_pool=self.db_pool,
                                    phone=self.user_data.phone_number,
                                    status="UPGRADE CHARGE",
                                    amount=balance,
                                )

                                await asyncio.sleep(delay=5)

                                continue

                        if available_energy < settings.MIN_AVAILABLE_ENERGY:
                            logger.info(f"{self.session_name} | Minimum energy reached: {available_energy}")
                            logger.info(f"{self.session_name} | Next sessions pack")

                            break

                except InvalidSession as error:
                    raise error

                except Exception as error:
                    logger.error(f"{self.session_name} | Unknown error: {error}")
                    await asyncio.sleep(delay=7)

                else:
                    sleep_between_clicks = randint(a=settings.SLEEP_BETWEEN_SLAP[0], b=settings.SLEEP_BETWEEN_SLAP[1])

                    if active_turbo is True:
                        sleep_between_clicks = 4

                    logger.info(f"Sleep {sleep_between_clicks}s")
                    await asyncio.sleep(delay=sleep_between_clicks)


async def run_slapper(tg_client: Client, db_pool: async_sessionmaker):
    try:
        if not local_db.get(tg_client.name):
            local_db[tg_client.name] = {'UserData': None, 'Token': '', 'Balance': 0, 'SlapLevel': 1}

        if not local_db[tg_client.name]['UserData']:
            async with tg_client:
                user_data = await tg_client.get_me()

                local_db[tg_client.name]['UserData'] = user_data
        else:
            user_data = local_db[tg_client.name]['UserData']

        proxy = None
        if settings.USE_PROXY_FROM_DB:
            proxy = await get_user_proxy(db_pool=db_pool, phone_number=user_data.phone_number)

        await Slapper(tg_client=tg_client, db_pool=db_pool, user_data=user_data).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
