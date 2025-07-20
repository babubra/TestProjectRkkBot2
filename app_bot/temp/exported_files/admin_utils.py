import datetime
import re

import httpx


async def get_non_working_days_re(html_content: str) -> list[datetime.date]:
    """
    Парсит HTML-код производственного календаря с помощью регулярных выражений
    и возвращает список нерабочих дней (выходных и праздников).

    Args:
        html_content: Строка, содержащая HTML-код страницы.

    Returns:
        Список объектов datetime.date, представляющих нерабочие дни.
    """
    non_working_days = []
    month_map = {
        "Январь": 1,
        "Февраль": 2,
        "Март": 3,
        "Апрель": 4,
        "Май": 5,
        "Июнь": 6,
        "Июль": 7,
        "Август": 8,
        "Сентябрь": 9,
        "Октябрь": 10,
        "Ноябрь": 11,
        "Декабрь": 12,
    }

    year_match = re.search(r"<h1>Производственный календарь на (\d{4}) год", html_content)
    if not year_match:
        print("Не удалось найти год на странице.")
        return []
    year = int(year_match.group(1))

    calendar_blocks = re.split(r'<table class="cal">', html_content)

    for block in calendar_blocks[1:]:
        month_match = re.search(r'<th[^>]+class="month"[^>]*>([^<]+)</th>', block)
        if not month_match:
            continue

        month_name = month_match.group(1).strip()
        month = month_map.get(month_name)
        if not month:
            continue

        weekend_day_matches = re.findall(
            r'<td[^>]+class="[^"]*weekend[^"]*"[^>]*>([^<]+)</', block
        )

        for day_text in weekend_day_matches:
            day_clean = re.sub(r"<[^>]+>|\*", "", day_text).strip()
            if day_clean.isdigit():
                day = int(day_clean)
                try:
                    date_obj = datetime.date(year, month, day)
                    non_working_days.append(date_obj)
                except ValueError:
                    continue

    return non_working_days


async def fetch_holidays_from_url(url: str) -> list[datetime.date]:
    """
    Загружает страницу по URL с помощью httpx, парсит её
    и возвращает список нерабочих дней.

    Args:
        url: URL-адрес страницы с производственным календарем.

    Returns:
        Список объектов datetime.date или пустой список в случае ошибки.
    """
    try:
        # Устанавливаем заголовок User-Agent, чтобы имитировать обычный браузер
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # Выполняем GET-запрос с поддержкой редиректов
        with httpx.Client(follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            # Проверяем, что запрос успешен (код 2xx)
            response.raise_for_status()
            html_content = response.text

        # Парсим HTML и возвращаем результат
        return await get_non_working_days_re(html_content)

    except httpx.RequestError as exc:
        print(f"Произошла ошибка при запросе к {exc.request.url!r}: {exc}")
        return []
    except httpx.HTTPStatusError as exc:
        print(
            f"Произошла ошибка ответа {exc.response.status_code} при запросе к {exc.request.url!r}."
        )
        return []
