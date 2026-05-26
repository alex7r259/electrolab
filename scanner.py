import os
import re
import sqlite3
import threading
from datetime import datetime

from docx import Document

DATABASE = 'protocols.db'

ROOT_FOLDER = r'\\Admin\рабочая'

OBJECT_MAP = {
    'БКПРУ-1': 'Б1',
    'БКПРУ-2': 'Б2',
    'БКПРУ-3': 'Б3',
    'БКПРУ-4': 'Б4',
    'СКРУ-1': 'С1',
    'СКРУ-2': 'С2',
    'СКРУ-3': 'С3',
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

scan_lock = threading.Lock()
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
        if re.search(rf'\b{re.escape(keyword)}', text):
            return test_type
    return 'Прочее'


def read_docx_text(path):
    try:
        if not os.path.exists(path):
            return ''
        doc = Document(path)
        text = []
        for p in doc.paragraphs[:40]:
            if p.text.strip():
                text.append(p.text.strip())
        return '\n'.join(text)
    except Exception as e:
        print(f'DOCX error: {e}')
        return ''


def get_header_text(text, max_lines=30):
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines[:max_lines])


def parse_protocol_header(text):
    header = get_header_text(text)

    data = {
        'object_name': '',
        'protocol_number': '',
        'protocol_title': '',
        'test_date': '',
        'engineers': '',
    }

    match = re.search(r'Объект:\s*(.+?)(?:\n|Проект:|Дата|Протокол)', header)
    if match:
        data['object_name'] = match.group(1).strip()

    match = re.search(
        r'Дата проведения испытаний:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})',
        header,
    )
    if match:
        data['test_date'] = match.group(1)

    match = re.search(r'Протокол\s*№\s*([0-9A-Za-zА-Яа-я\-–—]+)', header)
    if match:
        data['protocol_number'] = match.group(1)

    lines = header.split('\n')
    for i, line in enumerate(lines):
        if 'Протокол' in line and '№' in line:
            if i + 1 < len(lines):
                data['protocol_title'] = lines[i + 1].strip()
            break

    match = re.search(r'Испытания произвели:\s*(.+)', header)
    if match:
        data['engineers'] = match.group(1).strip()

    return data


def normalize_object_name(object_name):
    raw = (object_name or '').upper().replace(' ', '')
    mapping = {
        'БКПРУ-1': 'БКПРУ-1',
        'БКПРУ-2': 'БКПРУ-2',
        'БКПРУ-3': 'БКПРУ-3',
        'БКПРУ-4': 'БКПРУ-4',
        'БПКРУ-3': 'БКПРУ-3',
        'СКРУ-1': 'СКРУ-1',
        'СКРУ-2': 'СКРУ-2',
        'СКРУ-3': 'СКРУ-3',
        'СОЛИКАМСКСКРУ-1': 'СКРУ-1',
        'СОЛИКАМСКСКРУ-2': 'СКРУ-2',
        'СОЛИКАМСКСКРУ-3': 'СКРУ-3',
        'УСТЬ-ЯЙВИНСКИЙ': 'БКПРУ-3',
    }
    for key, value in mapping.items():
        if key in raw:
            return value
    return object_name


def add_protocol(parsed, protocol_name, object_code, test_type, content_text, file_path):
    try:
        conn = sqlite3.connect(DATABASE, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO protocols (
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
            None,
        ))
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        print(f'Уже существует: {file_path}')
    except Exception as e:
        print(f'Ошибка БД: {e}')


def scan_folders():
    global SCAN_RUNNING

    if SCAN_RUNNING:
        print('Сканирование уже выполняется')
        return

    SCAN_RUNNING = True
    print('Сканирование...')

    conn = sqlite3.connect(DATABASE, timeout=30)
    cursor = conn.cursor()

    try:
        existing_paths = set()

        cursor.execute(
            'SELECT file_path FROM protocols'
        )

        for row in cursor.fetchall():
            existing_paths.add(row[0])

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

                if full_path in existing_paths:
                    continue

                try:
                    protocol_name = os.path.splitext(file)[0]

                    content_text = read_docx_text(full_path)

                    if not content_text:
                        continue

                    parsed = parse_protocol_header(content_text)
                    parsed['object_name'] = normalize_object_name(parsed.get('object_name'))

                    test_type = detect_test_type(content_text)
                    modified_date = datetime.fromtimestamp(
                        os.path.getmtime(full_path)
                    ).strftime('%d.%m.%Y %H:%M')

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
                        full_path,
                        modified_date,
                    ))

                    print(f'Добавлен: {file}')

                except Exception as e:
                    print(f'Ошибка файла {file}: {e}')

        conn.commit()

    except Exception as e:
        print(f'Ошибка сканирования: {e}')

    finally:
        conn.close()
        SCAN_RUNNING = False
