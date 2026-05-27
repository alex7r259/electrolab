import os
import threading
import subprocess

from datetime import datetime

from flask import Flask
from flask import render_template
from flask import jsonify
from flask import request

from waitress import serve

from models import db, Protocol

from scanner import background_scan


app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///protocols.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {
        "check_same_thread": False
    }
}

db.init_app(app)


with app.app_context():
    db.create_all()


@app.route("/")
def index():

    protocols = Protocol.query.order_by(
        Protocol.test_date.desc()
    ).all()

    years = sorted(
        list(
            set(
                p.test_date.year
                for p in protocols
                if p.test_date
            )
        ),
        reverse=True
    )

    return render_template(
        "index.html",
        protocols=protocols,
        years=years
    )




@app.route("/print")
def print_protocols():

    year = request.args.get("year", type=int)

    query = Protocol.query

    if year:
        query = query.filter(db.extract("year", Protocol.test_date) == year)

    protocols = query.order_by(Protocol.test_date.asc()).all()

    years = [
        row[0]
        for row in db.session.query(
            db.extract("year", Protocol.test_date)
        ).filter(Protocol.test_date.isnot(None)).distinct().order_by(
            db.extract("year", Protocol.test_date).desc()
        ).all()
        if row[0]
    ]

    return render_template(
        "print.html",
        protocols=protocols,
        years=years,
        selected_year=year
    )


@app.route("/open/<int:protocol_id>")
def open_file(protocol_id):

    protocol = Protocol.query.get_or_404(protocol_id)

    path = protocol.file_path

    subprocess.Popen(
        f'explorer /select,"{path}"'
    )

    return jsonify({"success": True})


if __name__ == "__main__":

    scan_thread = threading.Thread(
        target=background_scan,
        args=(app,),
        daemon=True
    )

    scan_thread.start()

    print("WEB сервер запущен")

    serve(
        app,
        host="0.0.0.0",
        port=5000,
        threads=8
    )