# Установка и запуск проекта FlashScore

## Установка зависимостей
1. Убедитесь, что у вас установлен Python.
2. Установите необходимые зависимости, перейдя в корневую директорию проекта и выполните следующую команду:
    ```bash
    pip3 install -r requirements.txt
    ```

## Установка Playwright
После установки зависимостей выполните установку Playwright:
```bash
playwright install
```

## Запуск проекта
Для запуска сбора данных с сайта FlashScore используйте следующие команды:

1. Для сбора в JSON:
    ```bash
    scrapy crawl flashscore -o file.json:json
    ```

2. Для сбора в CSV:
    ```bash
    scrapy crawl flashscore -o file.csv:csv
    ```