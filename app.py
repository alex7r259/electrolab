from flask import Flask, render_template, request, send_file
import sqlite3

from apscheduler.schedulers.background import BackgroundScheduler

from scanner import scan_folders

app = Flask(__name__)

DATABASE = 'protocols.db'


def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS protocols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            protocol_number TEXT,
            protocol_name TEXT,
            object_code TEXT,
            object_name TEXT,
            protocol_title TEXT,
            test_date TEXT,
            engineers TEXT,
            test_type TEXT,
            cell_number TEXT,
            content_text TEXT,
            file_path TEXT UNIQUE,
            modified_date TEXT
        )
    ''')

    cursor.execute("PRAGMA table_info(protocols)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    required_columns = {
        'test_type': 'TEXT',
        'cell_number': 'TEXT',
        'content_text': 'TEXT',
        'object_name': 'TEXT',
        'protocol_title': 'TEXT',
        'test_date': 'TEXT',
        'engineers': 'TEXT',
    }

    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            cursor.execute(f'ALTER TABLE protocols ADD COLUMN {column_name} {column_type}')

    conn.commit()
    conn.close()


@app.route('/')
def index():
    search = request.args.get('search', '')
    object_filter = request.args.get('object_filter', '')
    type_filter = request.args.get('type_filter', '')

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = '''
        SELECT *
        FROM protocols
        WHERE
            (protocol_number LIKE ?
             OR protocol_name LIKE ?
             OR content_text LIKE ?)
    '''
    params = [f'%{search}%', f'%{search}%', f'%{search}%']

    if object_filter:
        query += ' AND object_code = ?'
        params.append(object_filter)

    if type_filter:
        query += ' AND test_type = ?'
        params.append(type_filter)

    query += ' ORDER BY modified_date DESC'

    cursor.execute(query, params)
    protocols = cursor.fetchall()
    conn.close()

    return render_template(
        'index.html',
        protocols=protocols,
        search=search,
        object_filter=object_filter,
        type_filter=type_filter,
    )


@app.route('/open/<int:id>')
def open_protocol(id):
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM protocols WHERE id=?', (id,))
    protocol = cursor.fetchone()
    conn.close()
    return send_file(protocol['file_path'])


if __name__ == '__main__':
    init_db()

    scheduler = BackgroundScheduler()
    scheduler.add_job(scan_folders, 'interval', minutes=5, max_instances=1)
    scheduler.start()

    app.run(debug=True)
