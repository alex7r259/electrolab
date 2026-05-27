import os
import re
import time

from datetime import datetime

import win32com.client
import tempfile

from docx import Document

from models import Protocol, db


SCAN_PATH = r"\\Admin\рабочая"

VALID_EXTENSIONS = [".docx", ".doc"]

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


def read_word_file(path):

    try:

        # DOCX
        if path.lower().endswith(".docx"):

            doc = Document(path)

            text = [p.text for p in doc.paragraphs]

            for table in doc.tables:

                for row in table.rows:

                    for cell in row.cells:
                        text.append(cell.text)

            return "\n".join(text)

        # DOC
        elif path.lower().endswith(".doc"):

            word = win32com.client.Dispatch("Word.Application")

            word.Visible = False

            doc = word.Documents.Open(path)

            text = doc.Content.Text

            doc.Close()

            word.Quit()

            return text

    except Exception as e:

        print(f"Ошибка чтения файла {path}: {e}")

        return ""

    return ""


def convert_doc_to_docx(path):

    word = win32com.client.Dispatch("Word.Application")

    doc = word.Documents.Open(path)

    new_path = path + "x"

    doc.SaveAs(new_path, FileFormat=16)

    doc.Close()

    word.Quit()

    return new_path


def extract_protocol_data(path):

    text = read_word_file(path)

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

    engineers = []

    try:

        # участок между "произвели" и "Руководитель"
        engineers_block = re.search(
            r"произвел(.*?)уководит",
            text,
            re.IGNORECASE | re.DOTALL
        )

        if engineers_block:

            block = engineers_block.group(1)

            found_engineers = re.findall(
                r"/\s*([А-ЯЁ][а-яё\-]+?\s+[А-Я]\.[А-Я]\.)\s*/",
                block
            )

            engineers = sorted(set(found_engineers))

    except Exception as e:

        print("Ошибка поиска инженеров:", e)

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

    engineers = ", ".join(engineers)

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

                    filename_lower = file.lower()

                    if file.startswith("~$"):
                        continue

                    if not is_protocol(file):
                        continue

                    if not (
                        filename_lower.endswith(".docx")
                        or filename_lower.endswith(".doc")
                    ):
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
