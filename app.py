from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import datetime

app = Flask(__name__)

DATABASE = 'protocols.db'

OBJECTS = {
    'Б1': 'БКПРУ-1',
    'Б2': 'БКПРУ-2',
    'Б3': 'БКПРУ-3',
    'Б4': 'БКПРУ-4',
    'С1': 'СКРУ-1',
    'С2': 'СКРУ-2',
    'С3': 'СКРУ-3'
}


def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS protocols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            protocol_number TEXT,
            object_code TEXT,
            protocol_name TEXT,
            object_name TEXT,
            customer TEXT,
            executor TEXT,
            protocol_date TEXT,
            notes TEXT
        )
    ''')
    conn.commit()
    conn.close()


def get_next_protocol_number(object_code):
    year = datetime.now().strftime('%y')
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    pattern = f'{year}-{object_code}-%'
    cursor.execute('''
        SELECT protocol_number
        FROM protocols
        WHERE protocol_number LIKE ?
        ORDER BY id DESC
        LIMIT 1
    ''', (pattern,))
    result = cursor.fetchone()
    conn.close()

    if result:
        last_number = int(result[0].split('-')[-1])
        next_number = last_number + 1
    else:
        next_number = 1

    return f'{year}-{object_code}-{next_number}'


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
               OR protocol_name LIKE ?
               OR object_name LIKE ?
               OR customer LIKE ?
               OR executor LIKE ?
            ORDER BY id DESC
        ''', (like, like, like, like, like))
    else:
        cursor.execute('SELECT * FROM protocols ORDER BY id DESC')

    protocols = cursor.fetchall()
    conn.close()
    return render_template('index.html', protocols=protocols, search=search)


@app.route('/add', methods=['GET', 'POST'])
def add_protocol():
    if request.method == 'POST':
        object_code = request.form['object_code']
        protocol_number = get_next_protocol_number(object_code)

        protocol_name = request.form['protocol_name']
        object_name = request.form['object_name']
        customer = request.form['customer']
        executor = request.form['executor']
        protocol_date = request.form['protocol_date']
        notes = request.form['notes']

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO protocols (
                protocol_number, object_code, protocol_name,
                object_name, customer, executor, protocol_date, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (protocol_number, object_code, protocol_name, object_name,
              customer, executor, protocol_date, notes))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))

    today = datetime.now().strftime('%Y-%m-%d')
    next_number = 'Будет присвоен автоматически'
    return render_template('add_protocol.html', today=today, objects=OBJECTS, next_number=next_number)


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_protocol(id):
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == 'POST':
        cursor.execute('''
            UPDATE protocols
            SET object_code=?, protocol_name=?, object_name=?, customer=?, executor=?, protocol_date=?, notes=?
            WHERE id=?
        ''', (
            request.form['object_code'],
            request.form['protocol_name'],
            request.form['object_name'],
            request.form['customer'],
            request.form['executor'],
            request.form['protocol_date'],
            request.form['notes'],
            id,
        ))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))

    cursor.execute('SELECT * FROM protocols WHERE id=?', (id,))
    protocol = cursor.fetchone()
    conn.close()

    if protocol is None:
        return redirect(url_for('index'))

    return render_template('edit_protocol.html', protocol=protocol, objects=OBJECTS)


@app.route('/delete/<int:id>')
def delete_protocol(id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM protocols WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
