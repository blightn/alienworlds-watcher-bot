from datetime import datetime, timedelta
import time
import requests
import http
import atexit
import shelve
import threading
import logging
import sys
import os
import shutil

import telebot
from telebot import types

from pathlib import Path
import environ


BASE_DIR = Path(__file__).resolve().parent

env = environ.Env()
environ.Env.read_env(str(BASE_DIR / '.env'))

TOKEN = env('TOKEN')
USERS_DB = env('DB')
DB_BACKUP_PATH = './backup/'
LOG = env('LOG')
TEST_FILE = 'test.bin'
ACTIONS_PER_REQUEST = 100
USER_POLL_INTERVAL = 5
REQUEST_WAIT_TIME = 10
REQUEST_INTERVAL = 5

STEP_DEFAULT = 0
STEP_ADD_USER = 1
STEP_DELETE_USER = 2

user_step = {}
http_lock = threading.Lock()
bot = telebot.TeleBot(token=TOKEN)


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message) -> None:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton('Аккаунты')
    item2 = types.KeyboardButton('Статистика')
    markup.add(item1, item2)
        
    bot.send_message(cid_from_message(message), f'Добро пожаловать, {message.from_user.first_name} {message.from_user.last_name}', reply_markup=markup)


@bot.message_handler(content_types=['text'])
#@bot.message_handler(func=lambda message: True, content_types=['text'])
def msg_handler(message) -> None:
    if message.chat.type == 'private':
        cid = cid_from_message(message)
        uid = uid_from_message(message)
        accounts = get_user_accounts(uid)
        step = get_user_step(uid)

        if step == STEP_DEFAULT:
            if message.text == 'Аккаунты':
                markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
                item1 = types.KeyboardButton('Вывести список аккаунтов')
                item2 = types.KeyboardButton('Добавить аккаунт(ы)')
                item3 = types.KeyboardButton('Удалить аккаунт(ы)')
                item4 = types.KeyboardButton('Удалить все аккаунты')
                item5 = types.KeyboardButton('Назад')
                markup.add(item1, item2, item3, item4, item5)

                bot.send_message(cid, f'Аккаунтов: {len(accounts)}', reply_markup=markup)
                    
            elif message.text == 'Статистика':
                markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
                item1 = types.KeyboardButton('Сегодня')
                item2 = types.KeyboardButton('Вчера')
                item3 = types.KeyboardButton('Назад')

                markup.add(item1, item2, item3)

                bot.send_message(cid, 'Выберите промежуток времени', reply_markup=markup)

            elif message.text == 'Вывести список аккаунтов':
                if len(accounts) > 0:
                    msg = ''
                    idx = 1
                    for account in accounts:
                        msg += f'{idx}. {account}\n'
                        idx += 1
                else:
                    msg = 'Необходимо добавить хотя бы один аккаунт'
                bot.send_message(cid, msg)

            elif message.text == 'Добавить аккаунт(ы)':
                set_user_step(uid, STEP_ADD_USER)
                bot.send_message(cid, 'Введите имя одного аккаунта или нескольких, разделённых запятыми (пример: "123.wam,abc.wam") или символами новой строки')

            elif message.text == 'Удалить аккаунт(ы)':
                if len(accounts) > 0:
                    set_user_step(uid, STEP_DELETE_USER)
                    msg = 'Введите имя одного аккаунта или нескольких, разделённых запятыми (пример: "123.wam,abc.wam") или символами новой строки'
                else:
                    msg = 'Список аккаунтов пуст'
                        
                bot.send_message(cid, msg)

            elif message.text == 'Удалить все аккаунты':
                if len(accounts) > 0:
                    delete_all_user_accounts(uid)
                    msg = 'Все аккаунты удалены'
                else:
                    msg = 'Список аккаунтов пуст'

                bot.send_message(cid, msg)

            elif message.text == 'Назад':
                send_welcome(message)

            elif message.text == 'Сегодня':
                time_after = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                time_before = time_after + timedelta(days=1)

                bot.send_message(cid, 'Идёт сбор статистики. Это может занять некоторое время. Продолжительность зависит от количества аккаутов пользователей в очереди на проверку, '
                    'а так же от сбора статистики каждый полный час')

                msg = '<b>Статистика за сегодня</b>\n\n' + count_tokens(uid, time_after, time_before, {})
                bot.send_message(cid, msg, parse_mode='html')

            elif message.text == 'Вчера':
                time_after = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                time_before = time_after
                time_after -= timedelta(days=1)

                bot.send_message(cid, 'Идёт сбор статистики. Это может занять некоторое время. Продолжительность зависит от количества аккаутов пользователей в очереди на проверку, '
                    'а так же от сбора статистики каждый полный час')

                msg = '<b>Статистика за вчера</b>\n\n' + count_tokens(uid, time_after, time_before, {})
                bot.send_message(cid, msg, parse_mode='html')
        else:
            if step == STEP_ADD_USER:
                text = message.text.strip()
                if ',' in text:
                    new_accounts = text.split(',')
                else:
                    new_accounts = text.splitlines()

                msg = f'Аккаунтов для добавления: <b>{len(new_accounts)}</b>\n\n'
                for account in new_accounts:
                    account = account.strip()
                    if is_account_valid(account):
                        if account in accounts:
                            msg += f'Аккаунт <b>{account}</b> уже добавлен\n'
                        else:
                            add_user_account(uid, account)
                            msg += f'Аккаунт <b>{account}</b> добавлен\n'
                    else:
                        msg += f'Неверное имя аккаунта: <b>{account}</b>\n'
                        
                set_user_step(uid, STEP_DEFAULT)
                bot.send_message(cid, msg, parse_mode='html')

            elif step == STEP_DELETE_USER:
                text = message.text.strip()
                if ',' in text:
                    new_accounts = text.split(',')
                else:
                    new_accounts = text.splitlines()

                msg = f'Аккаунтов для удаления: <b>{len(new_accounts)}</b>\n\n'
                for account in new_accounts:
                    account = account.strip()
                    if is_account_valid(account):
                        if account in accounts:
                            delete_user_account(uid, account)
                            msg += f'Аккаунт <b>{account}</b> удалён\n'
                        else:
                            msg += f'Аккаунта <b>{account}</b> нет в списке\n'
                    else:
                        msg += f'Неверное имя аккаунта: <b>{account}</b>\n'
                        
                set_user_step(uid, STEP_DEFAULT)
                bot.send_message(cid, msg, parse_mode='html')


def cid_from_message(message) -> int:
    return message.chat.id


def uid_from_message(message) -> str:
    return str(message.chat.id)


def uid_to_cid(uid) -> int:
    return int(uid)


def get_user_step(uid) -> int:
    if uid not in user_step:
        user_step[uid] = STEP_DEFAULT

    return user_step[uid]


def set_user_step(uid, step) -> None:
    user_step[uid] = step


def get_users_uids() -> list:
    return users_db.keys()


def get_user_accounts(uid) -> list:
    if uid not in users_db:
        users_db[uid] = []
        logging.info(f'New user {uid} added to DB')
        #save_users_accounts()

    return users_db[uid]


def add_user_account(uid, account) -> None:
    accounts = get_user_accounts(uid)
    if account not in accounts:
        tmp = users_db[uid]
        tmp.append(account)
        users_db[uid] = tmp
        #save_users_accounts()


def delete_user_account(uid, account) -> None:
    accounts = get_user_accounts(uid)
    if account in accounts:
        tmp = users_db[uid]
        tmp.remove(account)
        users_db[uid] = tmp
        #save_users_accounts()


def delete_all_user_accounts(uid) -> None:
    accounts = get_user_accounts(uid)
    if len(accounts) > 0:
        users_db[uid] = []
        #save_users_accounts()


def is_account_valid(account) -> bool:
    if not ' ' in account and account.isascii() and len(account) in range(5, 13) and account.endswith('.wam'):
        return True

    return False


# Не используется.
def load_users_accounts() -> bool:
    global users_db
    
    try:
        users_db = shelve.open(USERS_DB)
    except Exception as e:
        logging.exception(f'Exception in load_users_accounts(): {str(e)}, args: {str(e.args)}')
        return False

    return True


def count_tokens(uid, after, before, cache) -> str:
    accounts = get_user_accounts(uid)
    logging.debug(f'count_tokens() ENTER: uid: {uid}, after: {after}, before: {before}, accounts: {len(accounts)}')
    if len(accounts) > 0:
        after -= timedelta(hours=3) # GMT
        before -= timedelta(hours=3) # GMT
        iso_after = after.isoformat() + 'Z' # 2021-05-17T12:52:47.676728Z
        iso_before = before.isoformat() + 'Z' # 2021-05-17T12:52:47.676728Z

        tlm_price = get_token_price()
        msg = f'1 TLM = {tlm_price}$\n\n'
        idx = 1
        all_tokens = 0
        need_break = False

        http_lock.acquire()

        for account in accounts:
            tokens = 0.0
            total_actions = 0
            skip = 0

            while True:
                cache_used = False
                if float(cache.get(account, -1.0)) == -1.0 or total_actions != 0:
                    url = f'http://wax.eosrio.io/v2/history/get_actions?account={account}&filter=alien.worlds%3A*&limit={ACTIONS_PER_REQUEST}&skip={skip}&after={iso_after}&before={iso_before}&simple=true&noBinary=true'
                    logging.debug(f'count_tokens() GET: account: {account}, url: {url}')

                    try:
                        response = requests.get(url, timeout=30)
                    except Exception as e:
                        logging.exception(f'Exception in count_tokens() #1: {str(e)}, args: {str(e.args)}')
                        time.sleep(REQUEST_WAIT_TIME)
                        continue

                    logging.debug(f'count_tokens() RESPONSE: account: {account}, status code: {response.status_code}')

                    if response.status_code == http.HTTPStatus.TOO_MANY_REQUESTS or response.status_code == http.HTTPStatus.INTERNAL_SERVER_ERROR:
                        logging.error(f'TOO_MANY_REQUESTS or INTERNAL_SERVER_ERROR, status_code: {response.status_code}, uid: {uid}, url: {url}, data: {response.content}')
                        time.sleep(REQUEST_WAIT_TIME)
                        continue
                    elif response.status_code != http.HTTPStatus.OK:
                        logging.error(f'response.status_code != http.HTTPStatus.OK, status_code: {response.status_code}, uid: {uid}, url: {url}, data: {response.content}')
                        msg = '<b>Ошибка HTTP-запроса к API-серверу</b>\n'
                        need_break = True
                        break

                    try:
                        data = response.json()
                                
                        if total_actions == 0:
                            total_actions = data['total']['value']

                        for action in data['simple_actions']:
                            if action['contract'] == 'alien.worlds' and action['action'] == 'transfer' and action['data']['to'] == account and action['data']['symbol'] == 'TLM':
                                amount = float(action['data']['amount'])
                                tokens += amount

                                if float(cache.get(account, -1.0)) == -1.0:
                                    logging.info(f'Account {account} added to the cache')
                                    cache[account] = amount
                                else:
                                    cache[account] += amount

                    except Exception as e:
                        logging.exception(f'Exception in count_tokens() #2: {str(e)}, args: {str(e.args)}')
                        msg = '<b>Ошибка HTTP-ответа от API-сервера</b>\n'
                        need_break = True
                        break
                else:
                    tokens = float(cache[account])
                    total_actions = 0
                    cache_used = True
                    logging.info(f'Account {account} cached')

                skip += ACTIONS_PER_REQUEST
                total_actions -= ACTIONS_PER_REQUEST

                if not cache_used:
                    time.sleep(REQUEST_INTERVAL)

                if need_break or total_actions <= 0:
                    break

            if need_break:
                break

            usdt = tokens * tlm_price
            msg += f'{idx}. {account}: {tokens:g} TLM - {usdt:.2g}$\n'
            idx += 1
            all_tokens += tokens

        http_lock.release()

        if not need_break:
            usdt = all_tokens * tlm_price
            msg += f'\n<b>Всего: {all_tokens:g} TLM - {usdt:.2g}$</b>'
    else:
        msg = 'Список аккаунтов пуст'

    logging.debug(f'count_tokens() LEAVE: uid: {uid}, after: {after}, before: {before}, msg: {msg}')
    return msg


def get_token_price() -> float:
    url = 'https://api1.binance.com/api/v3/ticker/bookTicker?symbol=TLMUSDT'
    logging.debug(f'get_token_price() GET: url: {url}')
    
    try:
        response = requests.get(url, timeout=30)
    except Exception as e:
        logging.exception(f'Exception in get_token_price(): {str(e)}, args: {str(e.args)}')
        return 0.0

    logging.debug(f'get_token_price() RESPONSE: status code: {response.status_code}, data: {response.content}')
    if response.status_code == http.HTTPStatus.OK:
        data = response.json()
        price = float(data['askPrice'])
    else:
        price = 0.0
        logging.error(f'response.status_code != http.HTTPStatus.OK, status code: {response.status_code}, url: {url}, data: {response.content}')

    return price


def stat_thread_func(arg) -> None:
    while True:
        time_after = datetime.now().replace(minute=0, second=0, microsecond=0)
        time_before = time_after + timedelta(hours=1)
        time.sleep(time_before.timestamp() - time.time())

        cache = {}
        logging.info('Stat sending starts...')

        try:
            users_uids = get_users_uids()
            for uid in users_uids:
                logging.debug(f'Gathering stat for user: uid: {uid}, accounts: {get_user_accounts(uid)}')
                if len(get_user_accounts(uid)) > 0:
                    msg = '<b>Статистика за прошедший час</b>\n\n' + count_tokens(uid, time_after, time_before, cache)
                    bot.send_message(uid_to_cid(uid), msg, parse_mode='html')
                    time.sleep(USER_POLL_INTERVAL)
        except Exception as e:
            logging.exception(f'Exception in stat_thread_func(): {str(e)}, args: {str(e.args)}')

        cache.clear()
        logging.info(f'Stat sent to {len(users_uids)} users')


'''
def stat_thread_func(arg) -> None:
    while True:
        time_after = datetime.now().replace(minute=0, second=0, microsecond=0)
        time_before = time_after + timedelta(hours=1)
        #time_after = datetime.now().replace(minute=50, second=0, microsecond=0) # FOR DEBUG
        #time_before = time_after # FOR DEBUG
        #time_after -= timedelta(hours=1) # FOR DEBUG
        time.sleep(time_before.timestamp() - time.time())

        logging.info('Stat sending starts...')

        try:
            users_uids = get_users_uids()
            for uid in users_uids:
                logging.debug(f'Gathering stat for user: uid: {uid}, accounts: {get_user_accounts(uid)}')
                if len(get_user_accounts(uid)) > 0:
                    msg = '<b>Статистика за прошедший час</b>\n\n' + count_tokens(uid, time_after, time_before)

                    retries = 2
                    while retries > 0:
                        try:
                            bot.send_message(uid_to_cid(uid), msg, parse_mode='html')
                            break
                        except Exception as e:
                            logging.exception(f'Exception in stat_thread_func() - bot.send_message(): {str(e)}, args: {str(e.args)}')
                            logging.debug('Retrying...')
                            
                        retries -= 1
                        time.sleep(REQUEST_INTERVAL)

                    time.sleep(USER_POLL_INTERVAL)
        except Exception as e:
            logging.exception(f'Exception in stat_thread_func(): {str(e)}, args: {str(e.args)}')

        logging.info(f'Stat sent to {len(users_uids)} users')
'''


def exit_cleanup() -> None:
    try:
        users_db.close()
        backup_db()

        test_file.close()
        if os.path.exists(TEST_FILE):
            os.remove(TEST_FILE)
    except Exception as e:
        logging.exception(f'Exception in exit_cleanup(): {str(e)}, args: {str(e.args)}')


def backup_db() -> None:
    files_to_backup = (f'{USERS_DB}', f'{USERS_DB}.dat', f'{USERS_DB}.dir', f'{USERS_DB}.bak')

    if not os.path.exists(DB_BACKUP_PATH):
        os.mkdir(DB_BACKUP_PATH)

    prefix = DB_BACKUP_PATH + datetime.now().strftime('%H_%M_%S_')

    for f in files_to_backup:
        if os.path.exists(f):
            shutil.copyfile(f, f'{prefix}{f}')


if __name__ == "__main__":
    logging.basicConfig(
        level=env('LOG_LEVEL'),
        format='[%(asctime)s:%(msecs)03d][%(levelname)s]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(LOG),
            logging.StreamHandler()
        ]
    )

    if os.path.exists(TEST_FILE):
        logging.info('Already running. Exiting...')
        sys.exit(0)
    test_file = open(TEST_FILE, 'w')

    backup_db()

    try:
        users_db = shelve.open(USERS_DB)
    except Exception as e:
        logging.exception(f'Can\'t load DB {USERS_DB}, exception: {str(e)}, args: {str(e.args)}')
        sys.exit(1)

    atexit.register(exit_cleanup)

    stat_thread = threading.Thread(target=stat_thread_func, args=(1,), daemon=True)
    stat_thread.start()
    logging.info('Bot started')

    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logging.exception(f'Exception in polling(): {str(e)}, args: {str(e.args)}')
        
    logging.info('Bot stopped')
