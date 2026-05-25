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


def detect_test_type(text):
    text = text.lower()
    for keyword, test_type in TEST_TYPES.items():
        if keyword in text:
            return test_type
    return 'Прочее'


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


def extract_cell_number(text):
    match = re.search(r'яч\.?\s*№?\s*(\d+)', text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


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
        'object_name': '',
        'protocol_number': '',
        'protocol_title': '',
        'test_date': '',
        'engineers': '',
    }

    lines = text.split('\n')

    number_patterns = [
        r'протокол\s*№?\s*([\w\-\/]+)',
        r'([0-9]{2}-[А-ЯA-Z0-9]+-[0-9]+)',
    ]
    for pattern in number_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data['protocol_number'] = match.group(1)
            break

    for line in lines:
        if 'протокол' in line.lower():
            cleaned = re.sub(
                r'протокол\s*№?\s*[\w\-\/]+',
                '',
                line,
                flags=re.IGNORECASE,
            ).strip()
            if cleaned:
                data['protocol_title'] = cleaned
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

    date_patterns = [
        r'дата проведения испытаний[:\s]+([0-9\.]+)',
        r'от\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data['test_date'] = match.group(1)
            break

    engineer_patterns = [
        r'испытания произвели[:\s]+(.+)',
        r'испытания выполнили[:\s]+(.+)',
    ]
    for pattern in engineer_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data['engineers'] = match.group(1).strip()
            break

    return data


def add_protocol(parsed, protocol_name, object_code, test_type, content_text, file_path, modified_date, cell_number):
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
                modified_date,
                cell_number
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            cell_number,
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
                content_text = ''
                parsed = {}

                if file.lower().endswith('.docx'):
                    content_text = read_docx_text(full_path)
                    parsed = parse_protocol_data(content_text)

                if not parsed.get('protocol_number'):
                    parsed['protocol_number'] = protocol_number

                test_type = detect_test_type(file)
                modified_date = datetime.fromtimestamp(
                    os.path.getmtime(full_path)
                ).strftime('%d.%m.%Y %H:%M')

                combined_text = f'{file}\n{content_text}'
                cell_number = extract_cell_number(combined_text)

                add_protocol(
                    parsed,
                    protocol_name,
                    object_code,
                    test_type,
                    content_text,
                    full_path,
                    modified_date,
                    cell_number,
                )

                print(f'Добавлен: {file}')

    except Exception as e:
        print(f'Ошибка сканирования: {e}')
    finally:
        SCAN_RUNNING = False
