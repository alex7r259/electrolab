import os
import re
import sqlite3

from datetime import datetime

DATABASE = 'protocols.db'

ROOT_FOLDER = r'\\Admin\рабочая'

OBJECT_MAP = {

    'БКПРУ-1': 'Б1',
    'БКПРУ-2': 'Б2',
    'БКПРУ-3': 'Б3',
    'БКПРУ-4': 'Б4',

    'Соликамск СКРУ-1': 'С1',
    'Соликамск СКРУ-2': 'С2',
    'Соликамск СКРУ-3': 'С3',
}

# -----------------------------
# ЧЕРНЫЙ СПИСОК
# -----------------------------

IGNORE_WORDS = [

    'перечень',
    'титул',
    'договор',
    'служеб',
    'акт',
    'scan',
    'скан',
    'письмо',
    'путевка',
    'путёвка',
    'форма',
    'бланк',

]

# -----------------------------
# ПРОВЕРКА ФАЙЛА
# -----------------------------

def is_valid_protocol(filename):

    name = filename.lower()

    # временные файлы Word
    if name.startswith('~$'):
        return False

    # только docx/pdf
    if not name.endswith(('.docx', '.pdf')):
        return False

    # черный список
    for word in IGNORE_WORDS:

        if word in name:
            return False

    # обязательно должно быть слово протокол
    if 'протокол' not in name:
        return False

    return True


# -----------------------------
# ИЗВЛЕЧЕНИЕ НОМЕРА
# -----------------------------

def extract_protocol_number(filename):

    patterns = [

        r'(\d{2}-[А-ЯA-Z0-9]+-\d+)',

        r'протокол\s*№?\s*(\d+)',

        r'протокол\s*(\d+-\d+)',

        r'(\d+-\d+)',

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            filename,
            re.IGNORECASE
        )

        if match:
            return match.group(1)

    return None


# -----------------------------
# СОЗДАНИЕ ТАБЛИЦЫ
# -----------------------------

def init_scan_table():

    conn = sqlite3.connect(
        DATABASE,
        timeout=30
    )

    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scanned_protocols (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            protocol_number TEXT,
            object_code TEXT,

            protocol_name TEXT,

            file_name TEXT,

            file_path TEXT UNIQUE,

            scan_date TEXT
        )
    ''')

    conn.commit()

    conn.close()


# -----------------------------
# ДОБАВЛЕНИЕ
# -----------------------------

def add_protocol(

    protocol_number,
    object_code,
    protocol_name,
    file_name,
    file_path

):

    try:

        conn = sqlite3.connect(
            DATABASE,
            timeout=30
        )

        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR IGNORE INTO scanned_protocols (

                protocol_number,
                object_code,

                protocol_name,

                file_name,
                file_path,

                scan_date

            )

            VALUES (?, ?, ?, ?, ?, ?)

        ''', (

            protocol_number,
            object_code,

            protocol_name,

            file_name,
            file_path,

            datetime.now().isoformat()

        ))

        conn.commit()

        conn.close()

    except Exception as e:

        print(f'Ошибка БД: {e}')


# -----------------------------
# СКАНИРОВАНИЕ
# -----------------------------

SCAN_RUNNING = False

def scan_folders():

    global SCAN_RUNNING

    if SCAN_RUNNING:

        print('Сканирование уже выполняется')

        return

    SCAN_RUNNING = True

    print('Сканирование...')

    try:

        for root, dirs, files in os.walk(ROOT_FOLDER):

            object_code = None

            for folder_name, code in OBJECT_MAP.items():

                if folder_name in root:

                    object_code = code

                    break

            for file in files:

                if not is_valid_protocol(file):
                    continue

                full_path = os.path.join(root, file)

                protocol_number = extract_protocol_number(file)

                protocol_name = os.path.splitext(file)[0]

                add_protocol(

                    protocol_number,
                    object_code,

                    protocol_name,

                    file,
                    full_path

                )

                print(f'Добавлен: {file}')

    except Exception as e:

        print(f'Ошибка сканирования: {e}')

    finally:

        SCAN_RUNNING = False
