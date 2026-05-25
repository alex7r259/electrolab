import os
import re
import sqlite3

from datetime import datetime

from docx import Document

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

TEST_TYPES = {
    'ав': 'Автоматические выключатели',
    'изоляц': 'Сопротивление изоляции',
    'вви': 'Высоковольтные испытания',
    'петл': 'Петля фаза-ноль',
    'зазем': 'Заземление',
    'кабел': 'Кабельные линии',
    'узо': 'Проверка УЗО',
}

IGNORE_WORDS = [
    'перечень',
    'титул',
    'договор',
    'акт',
    'письмо',
    'бланк',
    'форма',
]

SCAN_RUNNING = False


def is_valid_protocol(filename):
    name = filename.lower()
    if not name.endswith('.docx'):
        return False
    if name.startswith('~$'):
        return False
    if 'протокол' not in name:
        return False
    for word in IGNORE_WORDS:
        if word in name:
            return False
    return True


def detect_test_type(text):
    text = text.lower()
    for keyword, test_type in TEST_TYPES.items():
        if keyword in text:
            return test_type
    return 'Прочее'


def read_docx_text(path):
    try:
        doc = Document(path)
        text = []
        for p in doc.paragraphs:
            if p.text.strip():
                text.append(p.text.strip())
        return '\n'.join(text)
    except Exception as e:
        print(f'DOCX error: {e}')
        return ''


def parse_protocol_data(text):
    data = {
        'protocol_number': '',
        'protocol_title': '',
        'object_name': '',
        'test_date': '',
        'engineers': '',
    }

    lines = text.split('\n')
    match = re.search(
        r'протокол\s*№?\s*([\w\-\/]+)',
        text,
        re.IGNORECASE,
    )
    if match:
        data['protocol_number'] = match.group(1).strip()

    for i, line in enumerate(lines):
        if 'протокол' in line.lower():
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if len(next_line) > 3:
                    data['protocol_title'] = next_line
                    break

    object_patterns = [
        r'объект[:\s]+(.+)',
        r'на объекте[:\s]+(.+)',
    ]
    for pattern in object_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data['object_name'] = match.group(1).strip()
            break

    match = re.search(
        r'дата проведения испытаний[:\s]+([0-9\.]+)',
        text,
        re.IGNORECASE,
    )
    if match:
        data['test_date'] = match.group(1)

    match = re.search(
        r'испытания произвели[:\s]+(.+)',
        text,
        re.IGNORECASE,
    )
    if match:
        data['engineers'] = match.group(1).strip()

    return data


def protocol_exists(path):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id FROM protocols WHERE file_path=?',
        (path,),
    )
    result = cursor.fetchone()
    conn.close()
    return result is not None


def add_protocol(parsed, protocol_name, object_code, test_type, content_text, file_path, modified_date):
    try:
        conn = sqlite3.connect(DATABASE, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO protocols (
                protocol_number,
                protocol_name,
                object_code,
                object_name,
                protocol_title,
                test_date,
                engineers,
                test_type,
                content_text,
                file_path,
                modified_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            parsed.get('protocol_number'),
            protocol_name,
            object_code,
            parsed.get('object_name'),
            parsed.get('protocol_title'),
            parsed.get('test_date'),
            parsed.get('engineers'),
            test_type,
            content_text,
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
        for root, _, files in os.walk(ROOT_FOLDER):
            object_code = None
            for folder_name, code in OBJECT_MAP.items():
                if folder_name in root:
                    object_code = code
                    break

            for file in files:
                if not is_valid_protocol(file):
                    continue

                full_path = os.path.join(root, file)
                if protocol_exists(full_path):
                    continue

                protocol_name = os.path.splitext(file)[0]
                content_text = ''
                parsed = {}

                content_text = read_docx_text(full_path)
                parsed = parse_protocol_data(content_text)

                test_type = detect_test_type(file)
                modified_date = datetime.fromtimestamp(
                    os.path.getmtime(full_path)
                ).strftime('%d.%m.%Y %H:%M')

                add_protocol(
                    parsed,
                    protocol_name,
                    object_code,
                    test_type,
                    content_text,
                    full_path,
                    modified_date,
                )

                print(f'Добавлен: {file}')

    except Exception as e:
        print(f'Ошибка сканирования: {e}')
    finally:
        SCAN_RUNNING = False
