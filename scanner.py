import os
import re
import time

from datetime import datetime

from docx import Document

from models import Protocol, db


SCAN_PATH = r"\\Admin\рабочая"

VALID_EXTENSIONS = [".docx"]

IGNORE_WORDS = [
    "перечень протоколов",
    "реестр протоколов",
    "журнал протоколов"
]


def is_protocol(filename):

    name = filename.lower()

    # временные файлы Word
    if name.startswith("~$"):
        return False

    if "протокол" not in name:
        return False

    ignore_words = [
        "перечень протоколов",
        "реестр протоколов",
        "журнал протоколов"
    ]

    for word in ignore_words:

        if word in name:
            return False

    return True


def extract_text_docx(path):

    try:

        if path.startswith("~$"):
            return ""

        doc = Document(path)

        text = []

        for p in doc.paragraphs:
            text.append(p.text)

        for table in doc.tables:

            for row in table.rows:

                for cell in row.cells:
                    text.append(cell.text)

        return "\n".join(text)

    except Exception as e:

        print(f"Ошибка чтения файла {path}: {e}")

        return ""


def extract_protocol_data(path):

    text = extract_text_docx(path)

    if not text:
        return None

    filename = os.path.basename(path)

    protocol_name = filename.replace(".docx", "").replace(".doc", "")

    object_match = re.search(
        r"Объект:\s*(.+)",
        text,
        re.IGNORECASE
    )

    date_match = re.search(
        r"Дата проведения испытаний:\s*(\d{2}\.\d{2}\.\d{4})",
        text,
        re.IGNORECASE
    )

    protocol_match = re.search(
        r"Протокол №\s*([^\n\r]+)",
        text,
        re.IGNORECASE
    )

    engineers = re.findall(
        r"/([А-Яа-яЁё\-]+\s?[А-Я]\.[А-Я]\.)/",
        text
    )

    object_name = object_match.group(1).strip() if object_match else ""

    protocol_number = protocol_match.group(1).strip() if protocol_match else ""

    try:

        test_date = datetime.strptime(
            date_match.group(1),
            "%d.%m.%Y"
        ).date()

    except:
        return None

    if test_date.year < 2022:
        return None

    engineers = ", ".join(sorted(set(engineers)))

    return {
        "protocol_number": protocol_number,
        "protocol_name": protocol_name,
        "object_name": object_name,
        "test_date": test_date,
        "engineers": engineers,
        "file_path": path
    }


def save_protocol(data):

    existing = Protocol.query.filter_by(
        file_path=data["file_path"]
    ).first()

    if existing:
        return

    protocol = Protocol(**data)

    db.session.add(protocol)
    db.session.commit()

    print(f"Добавлен: {data['protocol_name']}")


def scan_files(app):

    with app.app_context():

        print("Сканирование файлов...")

        for root, dirs, files in os.walk(SCAN_PATH):

            for file in files:

                try:

                    if not is_protocol(file):
                        continue

                    ext = os.path.splitext(file)[1].lower()

                    if ext not in VALID_EXTENSIONS:
                        continue

                    path = os.path.join(root, file)

                    data = extract_protocol_data(path)

                    if data:
                        save_protocol(data)

                except Exception as e:
                    print(e)

        print("Сканирование завершено")


def background_scan(app):

    while True:

        try:
            scan_files(app)

        except Exception as e:
            print("Ошибка сканирования:", e)

        time.sleep(300)
