# alienworlds-watcher-bot

Telegram-бот для игры Alien Worlds. Ведёт учёт токенов на аккаунтах и рассылает статистику каждый час либо по требованию.

### 1. Настроить
```
mkdir alienworlds-watcher-bot && cd $_
git clone git@github.com:blightn/alienworlds-watcher-bot.git .
virtualenv venv
source venv/bin/activate
(venv) pip install -r requirements.txt
```
### 2. Создать файл .env в корне
```
TOKEN=12345
DB=users.db
LOG=log.txt
LOG_LEVEL=INFO
```
### 3. Запустить
```
(venv) python bot.py
```
