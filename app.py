import json
import re
import os
import subprocess
import threading

from datetime import date, datetime, timedelta

import requests
from flask import Flask, jsonify, redirect, render_template, request, url_for
from sqlalchemy import or_
from waitress import serve

from models import ActionLog, Instrument, Protocol, db
from scanner import background_scan


app = Flask(__name__)
app.url_map.strict_slashes = False

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


def parse_date(raw_date: str | None) -> date | None:
    if not raw_date:
        return None
    return datetime.strptime(raw_date, "%Y-%m-%d").date()


def add_log(action: str, device_name: str, description: str) -> None:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    username = request.headers.get("X-User", "operator")

    log = ActionLog(
        action=action,
        device_name=device_name,
        description=description,
        username=username,
        ip_address=ip,
    )

    db.session.add(log)
    db.session.commit()


def extract_fgis_id(certificate_number: str) -> str | None:
    if not certificate_number:
        return None

    match = re.search(r"/(\d+)$", certificate_number)

    if not match:
        return None

    return match.group(1)


def load_fgis_data(certificate_number: str) -> dict | None:
    fgis_id = extract_fgis_id(certificate_number)

    if not fgis_id:
        return None

    url = f"https://fgis.gost.ru/fundmetrology/eapi/vri/{fgis_id}"

    try:
        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
        )

        if response.status_code != 200:
            return None

        return response.json()

    except requests.RequestException as error:
        print(error)
        return None


def build_fgis_view(fgis_data: dict | None) -> dict | None:
    if not fgis_data:
        return None

    result = fgis_data.get("result", {})
    mi = result.get("miInfo", {}).get("singleMI", {})
    vri = result.get("vriInfo", {})

    means = result.get("means", {})
    mieta = means.get("mieta", []) if isinstance(means, dict) else []
    etalons = []

    for item in mieta:
        if not isinstance(item, dict):
            continue
        etalons.append(
            {
                "title": item.get("title") or item.get("name") or item.get("type"),
                "modification": item.get("modification"),
                "number": item.get("number") or item.get("manufactureNum"),
                "reg_number": item.get("regNumber") or item.get("registryNumber"),
            }
        )

    return {
        "type_number": mi.get("mitypeNumber"),
        "type_title": mi.get("mitypeTitle"),
        "modification": mi.get("modification"),
        "manufacture_year": mi.get("manufactureYear"),
        "verification_date": vri.get("vrfDate"),
        "valid_date": vri.get("validDate"),
        "organization": vri.get("organization"),
        "method": vri.get("docTitle"),
        "cert_num": vri.get("applicable", {}).get("certNum"),
        "etalons": etalons,
    }


def update_instrument_dates_from_fgis(instrument: Instrument, fgis: dict | None) -> None:
    if not fgis:
        return

    try:
        if fgis.get("verification_date"):
            instrument.last_verification = datetime.strptime(
                fgis["verification_date"],
                "%d.%m.%Y",
            ).date()

        if fgis.get("valid_date"):
            instrument.next_verification = datetime.strptime(
                fgis["valid_date"],
                "%d.%m.%Y",
            ).date()

        db.session.commit()
    except (TypeError, ValueError):
        db.session.rollback()


@app.route("/")
def index():
    today = date.today()
    month_ahead = today + timedelta(days=30)
    current_year = today.year

    protocols = Protocol.query.order_by(Protocol.test_date.desc()).all()
    instruments_list = Instrument.query.all()

    years = sorted(
        list({p.test_date.year for p in protocols if p.test_date}),
        reverse=True,
    )

    protocol_stats = {
        "total": len(protocols),
        "current_year": sum(
            1
            for protocol in protocols
            if protocol.test_date and protocol.test_date.year == current_year
        ),
        "latest_date": next(
            (protocol.test_date for protocol in protocols if protocol.test_date),
            None,
        ),
    }

    instrument_stats = {
        "total": len(instruments_list),
        "active": sum(
            1
            for instrument in instruments_list
            if not instrument.written_off
            and not instrument.in_verification
            and instrument.next_verification
            and instrument.next_verification >= today
        ),
        "expired": sum(
            1
            for instrument in instruments_list
            if not instrument.written_off
            and instrument.next_verification
            and instrument.next_verification < today
        ),
        "upcoming": sum(
            1
            for instrument in instruments_list
            if not instrument.written_off
            and instrument.next_verification
            and today <= instrument.next_verification <= month_ahead
        ),
        "in_verification": sum(1 for instrument in instruments_list if instrument.in_verification),
        "written_off": sum(1 for instrument in instruments_list if instrument.written_off),
    }

    attention_instruments = [
        instrument
        for instrument in instruments_list
        if not instrument.written_off
        and instrument.next_verification
        and instrument.next_verification <= month_ahead
    ]
    attention_instruments.sort(key=lambda instrument: instrument.next_verification)

    return render_template(
        "index.html",
        protocol_stats=protocol_stats,
        instrument_stats=instrument_stats,
        recent_protocols=protocols[:5],
        attention_instruments=attention_instruments[:5],
        current_year=current_year,
        years=years,
        today=today,
    )


@app.route("/protocols")
def protocols():
    protocols_list = Protocol.query.order_by(Protocol.test_date.desc()).all()

    years = sorted(
        list({p.test_date.year for p in protocols_list if p.test_date}),
        reverse=True,
    )

    return render_template(
        "protocols.html",
        protocols=protocols_list,
        years=years,
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
        for row in db.session.query(db.extract("year", Protocol.test_date))
        .filter(Protocol.test_date.isnot(None))
        .distinct()
        .order_by(db.extract("year", Protocol.test_date).desc())
        .all()
        if row[0]
    ]

    return render_template(
        "print.html",
        protocols=protocols,
        years=years,
        selected_year=year,
    )


@app.route("/open/<int:protocol_id>")
def open_file(protocol_id):
    protocol = Protocol.query.get_or_404(protocol_id)
    path = protocol.file_path

    subprocess.Popen(f'explorer /select,"{path}"')

    return jsonify({"success": True})


@app.route("/instruments")
def instruments():
    search = request.args.get("search", "").strip()

    query = Instrument.query
    if search:
        add_log("SEARCH", "SYSTEM", f"Поиск: {search}")

        like_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Instrument.device_name.ilike(like_pattern),
                Instrument.test_types.ilike(like_pattern),
                Instrument.serial_number.ilike(like_pattern),
                Instrument.certificate_number.ilike(like_pattern),
                Instrument.passport_info.ilike(like_pattern),
                Instrument.note.ilike(like_pattern),
            )
        )

    instrument_items = query.order_by(
        Instrument.written_off.asc(),
        Instrument.next_verification.asc().nullslast(),
        Instrument.device_name.asc(),
    ).all()

    return render_template(
        "instruments.html",
        instruments=instrument_items,
        search=search,
        today=date.today(),
        month_ahead=date.today() + timedelta(days=30),
    )


@app.route("/instruments/add", methods=["POST"])
def add_instrument():
    instrument = Instrument(
        device_name=request.form.get("device_name", "").strip(),
        test_types=request.form.get("test_types", "").strip(),
        serial_number=request.form.get("serial_number", "").strip(),
        last_verification=parse_date(request.form.get("last_verification")),
        next_verification=parse_date(request.form.get("next_verification")),
        certificate_number=request.form.get("certificate_number", "").strip(),
        passport_info=request.form.get("passport_info", "").strip(),
        note=request.form.get("note", "").strip(),
        in_verification=request.form.get("in_verification") == "on",
        written_off=request.form.get("written_off") == "on",
    )
    db.session.add(instrument)
    db.session.commit()
    add_log(
        "ADD",
        instrument.device_name,
        f"Добавлено средство измерений № {instrument.serial_number}",
    )
    return redirect(url_for("instruments"))


@app.route("/instruments/edit/<int:instrument_id>", methods=["GET", "POST"])
def edit_instrument(instrument_id: int):
    instrument = Instrument.query.get_or_404(instrument_id)

    if request.method == "POST":
        changes = []
        fields = {
            "Наименование": (
                instrument.device_name,
                request.form.get("device_name", "").strip(),
            ),
            "Испытания": (
                instrument.test_types,
                request.form.get("test_types", "").strip(),
            ),
            "Заводской номер": (
                instrument.serial_number,
                request.form.get("serial_number", "").strip(),
            ),
            "Дата поверки": (
                instrument.last_verification,
                parse_date(request.form.get("last_verification")),
            ),
            "Действует до": (
                instrument.next_verification,
                parse_date(request.form.get("next_verification")),
            ),
            "Свидетельство": (
                instrument.certificate_number,
                request.form.get("certificate_number", "").strip(),
            ),
            "Паспорт": (
                instrument.passport_info,
                request.form.get("passport_info", "").strip(),
            ),
            "Примечание": (
                instrument.note,
                request.form.get("note", "").strip(),
            ),
            "Списан": (
                instrument.written_off,
                request.form.get("written_off") == "on",
            ),
            "В поверке": (
                instrument.in_verification,
                request.form.get("in_verification") == "on",
            ),
        }

        for field_name, values in fields.items():
            old_value, new_value = values
            if str(old_value) != str(new_value):
                changes.append(f"{field_name}: '{old_value}' → '{new_value}'")

        instrument.device_name = fields["Наименование"][1]
        instrument.test_types = fields["Испытания"][1]
        instrument.serial_number = fields["Заводской номер"][1]
        instrument.last_verification = fields["Дата поверки"][1]
        instrument.next_verification = fields["Действует до"][1]
        instrument.certificate_number = fields["Свидетельство"][1]
        instrument.passport_info = fields["Паспорт"][1]
        instrument.note = fields["Примечание"][1]
        instrument.written_off = fields["Списан"][1]
        instrument.in_verification = fields["В поверке"][1]
        db.session.commit()

        if changes:
            add_log("EDIT", instrument.device_name, " | ".join(changes))
        return redirect(url_for("instruments"))

    return render_template("edit_instrument.html", instrument=instrument)


@app.route("/instrument/<int:instrument_id>")
def instrument_card(instrument_id):
    instrument = Instrument.query.get_or_404(instrument_id)
    today = date.today()

    add_log(
        "VIEW",
        instrument.device_name,
        f"Открыта карточка прибора ID={instrument.id}",
    )

    use_cached = False
    if instrument.fgis_sync_date:
        delta = datetime.now() - instrument.fgis_sync_date
        if delta.total_seconds() < 86400:
            use_cached = True

    fgis_data = None
    if use_cached and instrument.fgis_data:
        try:
            fgis_data = json.loads(instrument.fgis_data)
        except json.JSONDecodeError:
            fgis_data = None

    if fgis_data is None:
        fgis_data = load_fgis_data(instrument.certificate_number)
        if fgis_data:
            instrument.fgis_data = json.dumps(fgis_data, ensure_ascii=False)
            instrument.fgis_sync_date = datetime.now()
            db.session.commit()
            add_log("FGIS_SYNC", instrument.device_name, "Синхронизация с ФГИС")

    fgis = build_fgis_view(fgis_data)
    update_instrument_dates_from_fgis(instrument, fgis)

    return render_template(
        "instrument_card.html",
        instrument=instrument,
        today=today,
        fgis=fgis,
    )


@app.route("/instruments/delete/<int:instrument_id>", methods=["POST"])
def delete_instrument(instrument_id: int):
    instrument = Instrument.query.get_or_404(instrument_id)
    add_log("DELETE", instrument.device_name, f"Удалено СИ № {instrument.serial_number}")
    db.session.delete(instrument)
    db.session.commit()
    return redirect(url_for("instruments"))


@app.route("/logs")
def logs():
    action_logs = ActionLog.query.order_by(ActionLog.created_at.desc()).all()

    return render_template(
        "logs.html",
        logs=action_logs,
    )


if __name__ == "__main__":
    if os.environ.get("ELECTROLAB_DISABLE_SCAN") != "1":
        scan_thread = threading.Thread(
            target=background_scan,
            args=(app,),
            daemon=True,
        )

        scan_thread.start()

    print("WEB сервер запущен")

    serve(
        app,
        host="0.0.0.0",
        port=5000,
        threads=8,
    )
