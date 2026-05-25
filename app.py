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

            file_path TEXT UNIQUE,

            modified_date TEXT

        )
    ''')
    conn.commit()
    conn.close()


@app.route('/')
def index():
    search = request.args.get('search', '').strip()
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if search:
        like = f'%{search}%'
        cursor.execute('''
            SELECT * FROM protocols
            WHERE protocol_number LIKE ?
               OR object_code LIKE ?
               OR protocol_name LIKE ?
               OR modified_date LIKE ?
            ORDER BY id DESC
        ''', (like, like, like, like))
    else:
        cursor.execute('SELECT * FROM protocols ORDER BY id DESC')

    protocols = cursor.fetchall()
    conn.close()
    return render_template('index.html', protocols=protocols, search=search)


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
