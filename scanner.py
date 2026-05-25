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

IGNORE_WORDS = [
    'перечень', 'титул', 'договор', 'служеб', 'акт', 'scan', 'скан',
    'письмо', 'путевка', 'путёвка', 'форма', 'бланк',
]

SCAN_RUNNING = False


def is_valid_protocol(filename):
    name = filename.lower()

    if name.startswith('~$'):
        return False

    if not name.endswith(('.docx', '.pdf')):
        return False

    for word in IGNORE_WORDS:
        if word in name:
            return False

    if 'протокол' not in name:
        return False

    return True


def extract_protocol_number(filename):
    patterns = [
        r'(\d{2}-[А-ЯA-Z0-9]+-\d+)',
        r'протокол\s*№?\s*(\d+)',
        r'протокол\s*(\d+-\d+)',
        r'(\d+-\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def add_protocol(protocol_number, protocol_name, object_code, file_path, modified_date):
    try:
        conn = sqlite3.connect(DATABASE, timeout=30)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR IGNORE INTO protocols (

                protocol_number,

                protocol_name,

                object_code,

                file_path,

                modified_date

            )

            VALUES (?, ?, ?, ?, ?)

        ''', (
            protocol_number,
            protocol_name,
            object_code,
            file_path,
            modified_date,
        ))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f'Ошибка БД: {e}')


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
                modified_date = datetime.fromtimestamp(
                    os.path.getmtime(full_path)
                ).strftime('%d.%m.%Y %H:%M')

                add_protocol(
                    protocol_number,
                    protocol_name,
                    object_code,
                    full_path,
                    modified_date,
                )

                print(f'Добавлен: {file}')

    except Exception as e:
        print(f'Ошибка сканирования: {e}')
    finally:
        SCAN_RUNNING = False
