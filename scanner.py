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


def extract_protocol_number(filename):
    patterns = [
        r'(\d{2}-[А-ЯA-Z0-9]+-\d+)',
        r'(\d{2}-\d+-\d+)',
        r'Протокол\s*(\d+-\d+)',
        r'(\d+-\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def init_scan_table():
    conn = sqlite3.connect(DATABASE)
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


def file_exists(path):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id
        FROM scanned_protocols
        WHERE file_path=?
    ''', (path,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def add_protocol(protocol_number, object_code, protocol_name, file_name, file_path):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO scanned_protocols (
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
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()


def scan_folders():
    print('Сканирование...')

    for root, dirs, files in os.walk(ROOT_FOLDER):
        object_code = None

        for folder_name, code in OBJECT_MAP.items():
            if folder_name in root:
                object_code = code
                break

        for file_name in files:
            if not file_name.lower().endswith(('.docx', '.pdf')):
                continue

            full_path = os.path.join(root, file_name)

            if file_exists(full_path):
                continue

            protocol_number = extract_protocol_number(file_name)
            protocol_name = os.path.splitext(file_name)[0]

            add_protocol(
                protocol_number,
                object_code,
                protocol_name,
                file_name,
                full_path,
            )

            print(f'Добавлен: {file_name}')
