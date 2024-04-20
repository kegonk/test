import scrapy
import re
from playwright.async_api import Page
from scrapy.http.response import Response
from scrapy import Spider
import json
import asyncio
import random


def get_unique_bookmakers(data):
    unique_bookmakers = set()
    for market in data.values():
        for time_frame in market.values():
            for bookmaker_data in time_frame.values():
                for bookmaker_entry in bookmaker_data:
                    unique_bookmakers.add(bookmaker_entry["Bookmaker"])

    return list(unique_bookmakers)


def get_odds_by_bookmaker(odds_data, bookmaker_name):
    odds = {}
    for bet_type, bet_data in odds_data.items():
        if bet_type == "Over/Under":
            for time, time_data in bet_data.items():
                for bookmaker, bookmaker_data in time_data.items():
                    if bookmaker == bookmaker_name:
                        for option in bookmaker_data:
                            if option["Total"] == "2.5":
                                odds["Over_2.5"] = str(option["Over"])
                                odds["Under_2.5"] = str(option["Under"])
    return odds


def get_bets(data, type, bookmaker_name, bet):
    if data.get(type, {}).get("Full Time", {}).get(bookmaker_name, []):
        return str(data[type]["Full Time"][bookmaker_name][0].get(bet, "X"))
    return "X"


def get_matches_id(data):
    matches_id = []
    matches = data.split("AA÷")
    for match in matches[1:]:
        parts = match.split("¬")
        matches_id.append(parts[0])
    return matches_id


def should_abort_request(request):
    if request.resource_type == "image" or ".jpg" in request.url or request.resource_type == "font":
        return True
    if request.method.lower() == "post":
        return True


class FlashscoreSpider(Spider):
    name = "flashscore"
    allowed_domains = ["flashscore.com"]
    start_urls = ["https://www.flashscore.com/football/england/premier-league/archive/"]
    custom_settings = {
        "TELNETCONSOLE_ENABLED": False,
        "ROBOTSTXT_OBEY": False,
        "LOG_LEVEL": "INFO",
        "LOGSTATS_INTERVAL": 2.5,
        "DOWNLOAD_TIMEOUT": 360,
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "USER_AGENT": None,
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "DEFAULT_REQUEST_HEADERS": None,
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": True,
            "channel": "chrome",
            "timeout": 35 * 1000,  # 35 seconds
            "devtools": False,
            "handle_sigint": False,
            "handle_sigterm": False,
            "handle_sighup": False,
            "args": [
                "--incognito",
                "--disable-gpu"
                "--disable-sync"
                "--disable-apps"
                "--disable-audio"
                "--disable-plugins"
                "--disable-infobars"
                "--disable-extensions"
                "--disable-translate"
                "--disable-geolocation"
                "--disable-notifications"
                "--disable-winsta"
                "--disable-dev-shm-usage"
                "--disable-webgl"
                "--disable-cache"
                "--disable-popup-blocking"
                "--disable-back-forward-cache"
                "--arc-disable-gms-core-cache"
                "--process-per-site"
                "--disable-offline-load-stale-cache"
                "--disk-cache-size=0"
                "--no-sandbox"
                "--disable-client-side-phishing-detection"
                "--disable-breakpad"
                "--ignore-certificate-errors",
                "--ignore-urlfetcher-cert-requests"
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--allow-running-insecure-content",
            ],
        },
        "PLAYWRIGHT_MAX_CONTEXTS": 1,
        "PLAYWRIGHT_MAX_PAGES_PER_CONTEXT": 1,
        "PLAYWRIGHT_ABORT_REQUEST": should_abort_request,
        "FEED_EXPORT_ENCODING": "utf-8",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 35 * 1000,
    }

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                dont_filter=True,
                meta={"dont_redirect": True},
            )

    def parse(self, response: Response):
        urls = response.xpath('.//*[@class="archive__season"]/a/@href').getall()
        for url in urls[1:]:
            year = int(url.strip("/").split('-')[-1])
            if year > 2009:
                yield response.follow(
                    url=f"{response.urljoin(url)}results/",
                    callback=self.parse_archive,
                    dont_filter=True,
                    meta={"dont_redirect": True},
                )

    def parse_archive(self, response: Response):
        matches = re.search("data: `(.*?)`", response.text)
        if matches:
            urls = get_matches_id(matches.group(1))
        else:
            urls = []

        for url in urls:
            yield scrapy.Request(
                url=f"https://www.flashscore.com/match/{url}/#/match-summary/match-summary",
                callback=self.parse_odds,
                dont_filter=True,
                meta={
                    "dont_redirect": True,
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_context_kwargs":{
                        "locale": "en-US"
                    }
                },
                errback=self.errback,
            )

    async def parse_odds(self, response: Response):
        page: Page = response.meta["playwright_page"]
        odds = await page.query_selector('a[href="#/odds-comparison"]')
        if odds:
            tournament = "".join(response.xpath('.//span[@class="tournamentHeader__country"]//text()').getall())
            time = response.xpath('.//div[@class="duelParticipant__startTime"]//text()').get("")
            t1 = "".join(response.xpath('.//div[@class="smv__incidentsHeader section__title"][1]/div[2]/text()').getall())
            score = " ".join(response.xpath('.//div[@class="detailScore__wrapper"]//text()').getall())
            name = " - ".join(response.xpath('.//div[@class="participant__participantNameWrapper"]//text()').getall())
            all_bets = {}

            await odds.click(delay=10)
            await asyncio.sleep(random.randint(1, 3))

            types_one = await page.query_selector_all('[class="filterOver filterOver--indent"] [data-testid="wcl-tabs"] a')
            for type1 in types_one:
                title_type1 = await type1.get_attribute("title")
                if title_type1 not in [
                    "1X2",
                    "Both teams to score",
                    "Double chance",
                    "Over/Under",
                ]:
                    continue
                if not all_bets.get(title_type1):
                    all_bets[title_type1] = {}
                await type1.click()
                types_two = await page.query_selector_all('[class="subFilterOver subFilterOver--indent"] [data-testid="wcl-tabs"] a')
                for type2 in types_two[:1]:
                    title_type2 = await type2.get_attribute("title")
                    if not all_bets[title_type1].get(title_type2):
                        all_bets[title_type1][title_type2] = {}
                    await type2.click()
                    headers = await page.query_selector_all('div[class="ui-table__header"] div')
                    headers = [await header.text_content() for header in headers]
                    all_prematch = await page.query_selector_all('[class="ui-table__row"]')
                    for prematch in all_prematch:
                        bet_name = await prematch.query_selector('img[class="prematchLogo"]')
                        bet_name = await bet_name.get_attribute("title")
                        if not all_bets[title_type1][title_type2].get(bet_name):
                            all_bets[title_type1][title_type2][bet_name] = []
                        odds = await prematch.query_selector_all("span")
                        odds = [await odd.text_content() for odd in odds]
                        result_dict = {key: value for key, value in zip(headers, [bet_name] + odds)}
                        all_bets[title_type1][title_type2][bet_name].append(result_dict)
            unique_bookmakers_list = get_unique_bookmakers(all_bets)
            for bookmaker in unique_bookmakers_list:
                tm = get_odds_by_bookmaker(all_bets, bookmaker)
                tb = get_odds_by_bookmaker(all_bets, bookmaker)
                yield {
                    "Ссылка": response.url.split("#")[0],
                    "Чемпионат": tournament,
                    "Дата": time,
                    "Т1": t1,
                    "Счет": score,
                    "Названия команд": name,
                    "БК": bookmaker,
                    "П1": get_bets(all_bets, "1X2", bookmaker, "1"),
                    "X": get_bets(all_bets, "1X2", bookmaker, "X"),
                    "П2": get_bets(all_bets, "1X2", bookmaker, "2"),
                    "ТМ2.5": tm.get("Under_2.5", "X"),
                    "ТБ2.5": tb.get("Over_2.5", "X"),
                    "ОЗ да": get_bets(
                        all_bets, "Both teams to score", bookmaker, "Yes"
                    ),
                    "1X": get_bets(all_bets, "Double chance", bookmaker, "1X"),
                    "2X": get_bets(all_bets, "Double chance", bookmaker, "X2"),
                }
        await page.close()

    async def errback(self, failure):
        page = failure.request.meta.get("playwright_page")
        if page is not None:
            await page.close()
