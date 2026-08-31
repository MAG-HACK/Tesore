
from flask import Flask, render_template, request, jsonify, session

import os
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from werkzeug.security import check_password_hash, generate_password_hash


# ============================================================
# APLICACIÓN
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "vertexmont_secret_2026_change_this"
)

app.permanent_session_lifetime = 60 * 60 * 24 * 7

# Cookies de sesión
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# En Render se utiliza HTTPS.
if os.environ.get("RENDER"):
    app.config["SESSION_COOKIE_SECURE"] = True


# ============================================================
# BASE DE DATOS SQLITE
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(BASE_DIR, "tesoreria.db")
)


# ============================================================
# ADMINISTRADOR
# ============================================================

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "admin"
)

DEFAULT_ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "admin123"
)


# ============================================================
# CATEGORÍAS PERMITIDAS
# ============================================================

ALLOWED_CATEGORIES = {
    "Ofrendas dominicales",
    "Donaciones",
    "Servicios",
    "Mantenimiento",
    "Alimentación",
    "Actividades de la iglesia",
    "Compras",
    "Transporte",
    "Otros"
}

ALLOWED_TYPES = {
    "ingreso",
    "gasto"
}


# ============================================================
# FECHA / HORA
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# CONEXIÓN SQLITE
# ============================================================

def get_db():
    """
    Abre una conexión a SQLite.
    """
    connection = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    connection.row_factory = sqlite3.Row

    # Permite claves foráneas.
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


# ============================================================
# INICIALIZAR BASE DE DATOS
# ============================================================

def init_db():
    """
    Crea las tablas necesarias si todavía no existen.
    """

    connection = get_db()

    try:
        cursor = connection.cursor()

        # ====================================================
        # TABLA DE MOVIMIENTOS
        # ====================================================

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                other_detail TEXT DEFAULT '',
                deleted_at TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT DEFAULT NULL
            )
            """
        )

        # ====================================================
        # TABLA DE ADMINISTRADOR
        # ====================================================

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS admin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT DEFAULT NULL
            )
            """
        )

        # ====================================================
        # CREAR ADMINISTRADOR SI NO EXISTE
        # ====================================================

        cursor.execute(
            """
            SELECT id
            FROM admin
            WHERE username = ?
            LIMIT 1
            """,
            (ADMIN_USERNAME,)
        )

        admin_exists = cursor.fetchone()

        if not admin_exists:
            password_hash = generate_password_hash(
                DEFAULT_ADMIN_PASSWORD
            )

            cursor.execute(
                """
                INSERT INTO admin (
                    username,
                    password,
                    created_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    ADMIN_USERNAME,
                    password_hash,
                    now_iso()
                )
            )

            print(
                "Administrador SQLite creado:",
                ADMIN_USERNAME
            )

        connection.commit()

    finally:
        connection.close()


# ============================================================
# CONVERTIR ROW SQLITE A DICCIONARIO
# ============================================================

def row_to_dict(row):
    if row is None:
        return None

    return dict(row)


# ============================================================
# RESPUESTA ESTÁNDAR DE ERROR
# ============================================================

def api_error(message, status=400):
    return jsonify({
        "ok": False,
        "error": message
    }), status


# ============================================================
# VALIDAR SESIÓN ADMINISTRATIVA
# ============================================================

def is_admin():
    return bool(
        session.get("admin", False)
    )


def require_admin():
    if not is_admin():
        return api_error(
            "No autorizado. Debes iniciar sesión como administrador.",
            401
        )

    return None


# ============================================================
# CONVERSIÓN DE MONTO
# ============================================================

def parse_amount(value):
    try:
        amount = Decimal(
            str(value).strip()
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError
    ):
        return None

    if amount <= 0:
        return None

    return amount


# ============================================================
# NORMALIZAR MOVIMIENTO
# ============================================================

def normalize_movement(movement):

    if not isinstance(movement, dict):
        return movement

    result = dict(movement)

    # Convertir monto a float.
    if "amount" in result:
        try:
            result["amount"] = float(
                result["amount"]
            )
        except (
            ValueError,
            TypeError
        ):
            pass

    # Compatibilidad con nombres alternativos.

    if "other_detail" not in result:
        if "otherDetail" in result:
            result["other_detail"] = result["otherDetail"]

    if "deleted_at" not in result:
        if "deletedAt" in result:
            result["deleted_at"] = result["deletedAt"]

    if "created_at" not in result:
        if "createdAt" in result:
            result["created_at"] = result["createdAt"]

    if "updated_at" not in result:
        if "updatedAt" in result:
            result["updated_at"] = result["updatedAt"]

    return result


# ============================================================
# CARGAR ADMINISTRADOR
# ============================================================

def load_admin():

    connection = get_db()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM admin
            WHERE username = ?
            LIMIT 1
            """,
            (ADMIN_USERNAME,)
        )

        row = cursor.fetchone()

        return row_to_dict(row)

    except Exception as error:

        print(
            "ERROR cargando administrador:",
            error
        )

        return None

    finally:
        connection.close()


# ============================================================
# PASSWORD
# ============================================================

def is_password_hash(value):

    value = str(
        value or ""
    )

    return (
        value.startswith("scrypt:")
        or value.startswith("pbkdf2:")
        or value.startswith("argon2:")
    )


def verify_password(
    stored_password,
    entered_password
):

    stored_password = str(
        stored_password or ""
    )

    entered_password = str(
        entered_password or ""
    )

    if not stored_password:
        return False

    if is_password_hash(
        stored_password
    ):

        try:
            return check_password_hash(
                stored_password,
                entered_password
            )

        except Exception as error:

            print(
                "ERROR verificando contraseña:",
                error
            )

            return False

    # Compatibilidad con contraseña antigua
    # guardada como texto plano.

    return stored_password == entered_password


# ============================================================
# GUARDAR HASH DE PASSWORD
# ============================================================

def save_admin_password(
    admin_data,
    password
):

    if not admin_data:
        return False

    admin_id = admin_data.get("id")

    if admin_id is None:
        return False

    password_hash = generate_password_hash(
        password
    )

    connection = get_db()

    try:

        connection.execute(
            """
            UPDATE admin
            SET
                password = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                password_hash,
                now_iso(),
                admin_id
            )
        )

        connection.commit()

        return True

    except Exception as error:

        print(
            "AVISO actualizando contraseña:",
            error
        )

        return False

    finally:
        connection.close()


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    try:

        connection = get_db()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM movements
            """
        )

        result = cursor.fetchone()

        total = result["total"]

        connection.close()

        return jsonify({
            "status": "ok",
            "database": True,
            "database_type": "sqlite",
            "database_path": DB_PATH,
            "movements": total
        })

    except Exception as error:

        print(
            "ERROR health:",
            error
        )

        return jsonify({
            "status": "error",
            "database": False,
            "database_type": "sqlite",
            "message": str(error)
        }), 500


# ============================================================
# AUTH — ESTADO
# ============================================================

@app.route(
    "/api/auth/status",
    methods=["GET"]
)
def auth_status():

    return jsonify({
        "ok": True,
        "authenticated": is_admin()
    })


# ============================================================
# AUTH — LOGIN
# ============================================================

@app.route(
    "/api/auth/login",
    methods=["POST"]
)
def auth_login():

    data = request.get_json(
        silent=True
    ) or {}

    username = str(
        data.get(
            "username",
            ""
        )
    ).strip()

    password = str(
        data.get(
            "password",
            ""
        )
    )

    if not username or not password:

        return api_error(
            "Introduce usuario y contraseña.",
            400
        )

    if username != ADMIN_USERNAME:

        return api_error(
            "Usuario o contraseña incorrectos.",
            401
        )

    admin_data = load_admin()

    if not admin_data:

        return api_error(
            "No se pudo cargar la configuración del administrador.",
            500
        )

    stored_username = str(
        admin_data.get(
            "username",
            ADMIN_USERNAME
        )
    ).strip()

    stored_password = str(
        admin_data.get(
            "password",
            ""
        )
    )

    if username != stored_username:

        return api_error(
            "Usuario o contraseña incorrectos.",
            401
        )

    password_correct = verify_password(
        stored_password,
        password
    )

    # Si la contraseña antigua estaba
    # en texto plano, convertirla a hash.

    if (
        password_correct
        and stored_password
        and not is_password_hash(
            stored_password
        )
    ):

        save_admin_password(
            admin_data,
            password
        )

    if not password_correct:

        return api_error(
            "Usuario o contraseña incorrectos.",
            401
        )

    # Crear sesión.

    session.clear()

    session["admin"] = True
    session["username"] = ADMIN_USERNAME

    session.permanent = True

    return jsonify({
        "ok": True,
        "authenticated": True
    })


# ============================================================
# AUTH — LOGOUT
# ============================================================

@app.route(
    "/api/auth/logout",
    methods=["POST"]
)
def auth_logout():

    session.clear()

    return jsonify({
        "ok": True,
        "authenticated": False
    })


# ============================================================
# CONSTRUIR FILTROS SQLITE
# ============================================================

def build_movement_filters(
    include_deleted=False
):

    conditions = []
    parameters = []

    # ========================================================
    # ELIMINADOS / ACTIVOS
    # ========================================================

    deleted = str(
        request.args.get(
            "deleted",
            ""
        )
    ).strip().lower()

    if deleted == "true":
        include_deleted = True

    if include_deleted:

        conditions.append(
            "deleted_at IS NOT NULL"
        )

    else:

        conditions.append(
            "deleted_at IS NULL"
        )

    # ========================================================
    # BÚSQUEDA
    # ========================================================

    search = str(
        request.args.get(
            "search",
            ""
        )
    ).strip()

    if search:

        conditions.append(
            """
            (
                description LIKE ?
                OR other_detail LIKE ?
                OR category LIKE ?
            )
            """
        )

        search_value = f"%{search}%"

        parameters.extend([
            search_value,
            search_value,
            search_value
        ])

    # ========================================================
    # FECHA DESDE
    # ========================================================

    date_from = str(
        request.args.get(
            "from",
            ""
        )
    ).strip()

    if date_from:

        conditions.append(
            "date >= ?"
        )

        parameters.append(
            date_from
        )

    # ========================================================
    # FECHA HASTA
    # ========================================================

    date_to = str(
        request.args.get(
            "to",
            ""
        )
    ).strip()

    if date_to:

        conditions.append(
            "date <= ?"
        )

        parameters.append(
            date_to
        )

    # ========================================================
    # TIPO
    # ========================================================

    movement_type = str(
        request.args.get(
            "type",
            ""
        )
    ).strip()

    if movement_type in ALLOWED_TYPES:

        conditions.append(
            "type = ?"
        )

        parameters.append(
            movement_type
        )

    # ========================================================
    # CATEGORÍA
    # ========================================================

    category = str(
        request.args.get(
            "category",
            ""
        )
    ).strip()

    if category in ALLOWED_CATEGORIES:

        conditions.append(
            "category = ?"
        )

        parameters.append(
            category
        )

    where_sql = ""

    if conditions:

        where_sql = (
            "WHERE "
            + " AND ".join(
                conditions
            )
        )

    return where_sql, parameters


# ============================================================
# API — OBTENER MOVIMIENTOS
# ============================================================

@app.route(
    "/api/movements",
    methods=["GET"]
)
def get_movements():

    try:

        deleted_requested = (
            request.args.get(
                "deleted",
                ""
            ).lower() == "true"
        )

        # El historial eliminado requiere
        # sesión administrativa.

        if deleted_requested:

            unauthorized = require_admin()

            if unauthorized:
                return unauthorized

        # ====================================================
        # LIMIT
        # ====================================================

        try:

            limit = int(
                request.args.get(
                    "limit",
                    "10"
                )
            )

        except ValueError:

            limit = 10

        # ====================================================
        # OFFSET
        # ====================================================

        try:

            offset = int(
                request.args.get(
                    "offset",
                    "0"
                )
            )

        except ValueError:

            offset = 0

        # Límites de seguridad.

        limit = max(
            1,
            min(
                limit,
                500
            )
        )

        offset = max(
            0,
            offset
        )

        # ====================================================
        # FILTROS
        # ====================================================

        where_sql, parameters = (
            build_movement_filters(
                include_deleted=deleted_requested
            )
        )

        connection = get_db()
        cursor = connection.cursor()

        # ====================================================
        # TOTAL
        # ====================================================

        cursor.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM movements
            {where_sql}
            """,
            parameters
        )

        total = cursor.fetchone()["total"]

        # ====================================================
        # MOVIMIENTOS
        # ====================================================

        cursor.execute(
            f"""
            SELECT *
            FROM movements
            {where_sql}
            ORDER BY date DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            parameters + [
                limit,
                offset
            ]
        )

        rows = cursor.fetchall()

        connection.close()

        movements = [
            normalize_movement(
                row_to_dict(row)
            )
            for row in rows
        ]

        return jsonify({
            "ok": True,
            "movements": movements,
            "total": total,
            "limit": limit,
            "offset": offset
        })

    except Exception as error:

        print(
            "ERROR en /api/movements:",
            error
        )

        return api_error(
            "Error interno cargando los movimientos.",
            500
        )


# ============================================================
# API — OBTENER UN MOVIMIENTO
# ============================================================

@app.route(
    "/api/movements/<movement_id>",
    methods=["GET"]
)
def get_movement(
    movement_id
):

    try:

        try:

            movement_id = int(
                movement_id
            )

        except ValueError:

            return api_error(
                "ID de movimiento inválido.",
                400
            )

        connection = get_db()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM movements
            WHERE id = ?
            LIMIT 1
            """,
            (movement_id,)
        )

        row = cursor.fetchone()

        connection.close()

        if not row:

            return api_error(
                "Movimiento no encontrado.",
                404
            )

        movement = normalize_movement(
            row_to_dict(row)
        )

        return jsonify({
            "ok": True,
            "movement": movement
        })

    except Exception as error:

        print(
            "ERROR obteniendo movimiento:",
            error
        )

        return api_error(
            "Error interno obteniendo el movimiento.",
            500
        )


# ============================================================
# VALIDAR DATOS DEL MOVIMIENTO
# ============================================================

def validate_movement_data(data):

    if not isinstance(data, dict):

        return None, "Datos inválidos."

    # ========================================================
    # TIPO
    # ========================================================

    movement_type = str(
        data.get(
            "type",
            ""
        )
    ).strip()

    if movement_type not in ALLOWED_TYPES:

        return None, (
            "El tipo de movimiento no es válido."
        )

    # ========================================================
    # MONTO
    # ========================================================

    amount = parse_amount(
        data.get("amount")
    )

    if amount is None:

        return None, (
            "El monto debe ser mayor que 0."
        )

    # ========================================================
    # DESCRIPCIÓN
    # ========================================================

    description = str(
        data.get(
            "description",
            ""
        )
    ).strip()

    if not description:

        return None, (
            "La descripción es obligatoria."
        )

    if len(description) > 180:

        return None, (
            "La descripción no puede superar "
            "los 180 caracteres."
        )

    # ========================================================
    # FECHA
    # ========================================================

    movement_date = str(
        data.get(
            "date",
            ""
        )
    ).strip()

    if not movement_date:

        return None, (
            "La fecha es obligatoria."
        )

    # Validar YYYY-MM-DD.

    try:

        datetime.strptime(
            movement_date,
            "%Y-%m-%d"
        )

    except ValueError:

        return None, (
            "La fecha no tiene un formato válido."
        )

    # ========================================================
    # CATEGORÍA
    # ========================================================

    category = str(
        data.get(
            "category",
            ""
        )
    ).strip()

    if category not in ALLOWED_CATEGORIES:

        return None, (
            "La categoría no es válida."
        )

    # ========================================================
    # DETALLE DE OTROS
    # ========================================================

    other_detail = str(
        data.get(
            "other_detail",
            data.get(
                "otherDetail",
                ""
            )
        )
    ).strip()

    if category == "Otros":

        if not other_detail:

            return None, (
                "Debes especificar el concepto de 'Otros'."
            )

        if len(other_detail) > 180:

            return None, (
                "El detalle de 'Otros' no puede "
                "superar los 180 caracteres."
            )

    else:

        other_detail = ""

    # ========================================================
    # DATOS LIMPIOS
    # ========================================================

    clean_data = {
        "type": movement_type,
        "amount": float(amount),
        "description": description,
        "date": movement_date,
        "category": category,
        "other_detail": other_detail
    }

    return clean_data, None


# ============================================================
# API — CREAR MOVIMIENTO
# ============================================================

@app.route(
    "/api/movements",
    methods=["POST"]
)
def create_movement():

    unauthorized = require_admin()

    if unauthorized:
        return unauthorized

    try:

        data = request.get_json(
            silent=True
        ) or {}

        movement, error = (
            validate_movement_data(
                data
            )
        )

        if error:

            return api_error(
                error,
                400
            )

        created_at = now_iso()

        connection = get_db()
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO movements (
                type,
                amount,
                description,
                date,
                category,
                other_detail,
                deleted_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, NULL)
            """,
            (
                movement["type"],
                movement["amount"],
                movement["description"],
                movement["date"],
                movement["category"],
                movement["other_detail"],
                created_at
            )
        )

        movement_id = cursor.lastrowid

        connection.commit()

        # Obtener movimiento creado.

        cursor.execute(
            """
            SELECT *
            FROM movements
            WHERE id = ?
            LIMIT 1
            """,
            (movement_id,)
        )

        row = cursor.fetchone()

        connection.close()

        created = normalize_movement(
            row_to_dict(row)
        )

        return jsonify({
            "ok": True,
            "movement": created
        }), 201

    except Exception as error:

        print(
            "ERROR en creación de movimiento:",
            error
        )

        return api_error(
            "Error interno guardando el movimiento.",
            500
        )


# ============================================================
# API — EDITAR MOVIMIENTO
# ============================================================

@app.route(
    "/api/movements/<movement_id>",
    methods=["PUT"]
)
def update_movement(
    movement_id
):

    unauthorized = require_admin()

    if unauthorized:
        return unauthorized

    try:

        try:

            movement_id = int(
                movement_id
            )

        except ValueError:

            return api_error(
                "ID de movimiento inválido.",
                400
            )

        data = request.get_json(
            silent=True
        ) or {}

        movement, error = (
            validate_movement_data(
                data
            )
        )

        if error:

            return api_error(
                error,
                400
            )

        # ====================================================
        # VERIFICAR EXISTENCIA
        # ====================================================

        connection = get_db()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM movements
            WHERE id = ?
            LIMIT 1
            """,
            (movement_id,)
        )

        existing_row = cursor.fetchone()

        if not existing_row:

            connection.close()

            return api_error(
                "Movimiento no encontrado.",
                404
            )

        existing = row_to_dict(
            existing_row
        )

        # ====================================================
        # VERIFICAR QUE ESTÉ ACTIVO
        # ====================================================

        if existing.get("deleted_at"):

            connection.close()

            return api_error(
                "No puedes editar un movimiento eliminado.",
                400
            )

        # ====================================================
        # ACTUALIZAR
        # ====================================================

        cursor.execute(
            """
            UPDATE movements
            SET
                type = ?,
                amount = ?,
                description = ?,
                date = ?,
                category = ?,
                other_detail = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                movement["type"],
                movement["amount"],
                movement["description"],
                movement["date"],
                movement["category"],
                movement["other_detail"],
                now_iso(),
                movement_id
            )
        )

        connection.commit()

        # Obtener movimiento actualizado.

        cursor.execute(
            """
            SELECT *
            FROM movements
            WHERE id = ?
            LIMIT 1
            """,
            (movement_id,)
        )

        updated_row = cursor.fetchone()

        connection.close()

        updated = normalize_movement(
            row_to_dict(updated_row)
        )

        return jsonify({
            "ok": True,
            "movement": updated
        })

    except Exception as error:

        print(
            "ERROR editando movimiento:",
            error
        )

        return api_error(
            "Error interno actualizando el movimiento.",
            500
        )


# ============================================================
# API — ELIMINAR MOVIMIENTO
# ============================================================
#
# IMPORTANTE:
#
# NO se borra físicamente de SQLite.
#
# Solamente se coloca deleted_at.
#
# De esta manera:
#
# - desaparece de los movimientos activos
# - deja de afectar el saldo
# - permanece en historial administrativo
# - puede restaurarse posteriormente
#
# ============================================================

@app.route(
    "/api/movements/<movement_id>",
    methods=["DELETE"]
)
def delete_movement(
    movement_id
):

    unauthorized = require_admin()

    if unauthorized:
        return unauthorized

    try:

        try:

            movement_id = int(
                movement_id
            )

        except ValueError:

            return api_error(
                "ID de movimiento inválido.",
                400
            )

        connection = get_db()
        cursor = connection.cursor()

        # ====================================================
        # VERIFICAR EXISTENCIA
        # ====================================================

        cursor.execute(
            """
            SELECT *
            FROM movements
            WHERE id = ?
            LIMIT 1
            """,
            (movement_id,)
        )

        existing_row = cursor.fetchone()

        if not existing_row:

            connection.close()

            return api_error(
                "Movimiento no encontrado.",
                404
            )

        existing = row_to_dict(
            existing_row
        )

        # ====================================================
        # VERIFICAR SI YA ESTÁ ELIMINADO
        # ====================================================

        if existing.get("deleted_at"):

            connection.close()

            return api_error(
                "El movimiento ya fue eliminado.",
                400
            )

        # ====================================================
        # ELIMINACIÓN LÓGICA
        # ====================================================

        deleted_at = now_iso()

        cursor.execute(
            """
            UPDATE movements
            SET
                deleted_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                deleted_at,
                deleted_at,
                movement_id
            )
        )

        connection.commit()

        # Obtener movimiento eliminado.

        cursor.execute(
            """
            SELECT *
            FROM movements
            WHERE id = ?
            LIMIT 1
            """,
            (movement_id,)
        )

        deleted_row = cursor.fetchone()

        connection.close()

        deleted = normalize_movement(
            row_to_dict(deleted_row)
        )

        return jsonify({
            "ok": True,
            "movement": deleted
        })

    except Exception as error:

        print(
            "ERROR eliminando movimiento:",
            error
        )

        return api_error(
            "Error interno eliminando el movimiento.",
            500
        )


# ============================================================
# API — ELIMINAR MOVIMIENTO PERMANENTEMENTE
# ============================================================
#
# ESTA ES LA RUTA NUEVA.
#
# Solo un administrador puede utilizarla.
#
# Solo permite eliminar físicamente movimientos que ya
# estén eliminados mediante deleted_at.
#
# Una vez ejecutado:
#
# DELETE FROM movements
#
# el movimiento desaparece definitivamente de SQLite y
# NO puede ser restaurado.
#
# ============================================================

@app.route(
    "/api/movements/<movement_id>/permanent",
    methods=["DELETE"]
)
def permanently_delete_movement(
    movement_id
):

    unauthorized = require_admin()

    if unauthorized:
        return unauthorized

    try:

        try:

            movement_id = int(
                movement_id
            )

        except ValueError:

            return api_error(
                "ID de movimiento inválido.",
                400
            )

        connection = get_db()
        cursor = connection.cursor()

        # ====================================================
        # VERIFICAR EXISTENCIA
        # ====================================================

        cursor.execute(
            """
            SELECT *
            FROM movements
            WHERE id = ?
            LIMIT 1
            """,
            (movement_id,)
        )

        existing_row = cursor.fetchone()

        if not existing_row:

            connection.close()

            return api_error(
                "Movimiento no encontrado.",
                404
            )

        existing = row_to_dict(
            existing_row
        )

        # ====================================================
        # SOLO SE PUEDE BORRAR PERMANENTEMENTE
        # UN MOVIMIENTO QUE YA ESTÉ ELIMINADO
        # ====================================================

        if not existing.get("deleted_at"):

            connection.close()

            return api_error(
                "El movimiento debe estar eliminado antes de poder borrarlo permanentemente.",
                400
            )

        # ====================================================
        # ELIMINACIÓN FÍSICA
        # ====================================================

        cursor.execute(
            """
            DELETE FROM movements
            WHERE id = ?
            """,
            (movement_id,)
        )

        # Verificar que realmente se haya eliminado.

        if cursor.rowcount != 1:

            connection.rollback()
            connection.close()

            return api_error(
                "No se pudo eliminar permanentemente el movimiento.",
                500
            )

        connection.commit()

        connection.close()

        # ====================================================
        # RESPUESTA
        # ====================================================

        return jsonify({
            "ok": True,
            "message": "El movimiento fue eliminado permanentemente.",
            "movement_id": movement_id
        })

    except Exception as error:

        print(
            "ERROR eliminando permanentemente movimiento:",
            error
        )

        try:
            connection.rollback()
            connection.close()
        except Exception:
            pass

        return api_error(
            "Error interno eliminando permanentemente el movimiento.",
            500
        )


# ============================================================
# API — HISTORIAL ADMINISTRATIVO
# ============================================================

@app.route(
    "/api/admin/history",
    methods=["GET"]
)
def admin_history():

    unauthorized = require_admin()

    if unauthorized:
        return unauthorized

    try:

        connection = get_db()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM movements
            WHERE deleted_at IS NOT NULL
            ORDER BY deleted_at DESC, id DESC
            LIMIT 500
            """
        )

        rows = cursor.fetchall()

        connection.close()

        movements = [
            normalize_movement(
                row_to_dict(row)
            )
            for row in rows
        ]

        return jsonify({
            "ok": True,
            "movements": movements,
            "history": movements,
            "deleted_movements": movements
        })

    except Exception as error:

        print(
            "ERROR en historial administrativo:",
            error
        )

        return api_error(
            "Error interno cargando el historial administrativo.",
            500
        )


# ============================================================
# API — RESTAURAR MOVIMIENTO
# ============================================================

@app.route(
    "/api/movements/<movement_id>/restore",
    methods=["POST"]
)
def restore_movement(
    movement_id
):

    unauthorized = require_admin()

    if unauthorized:
        return unauthorized

    try:

        try:

            movement_id = int(
                movement_id
            )

        except ValueError:

            return api_error(
                "ID de movimiento inválido.",
                400
            )

        connection = get_db()
        cursor = connection.cursor()

        # ====================================================
        # VERIFICAR MOVIMIENTO
        # ====================================================

        cursor.execute(
            """
            SELECT *
            FROM movements
            WHERE id = ?
            LIMIT 1
            """,
            (movement_id,)
        )

        existing_row = cursor.fetchone()

        if not existing_row:

            connection.close()

            return api_error(
                "Movimiento no encontrado.",
                404
            )

        existing = row_to_dict(
            existing_row
        )

        # ====================================================
        # VERIFICAR QUE ESTÉ ELIMINADO
        # ====================================================

        if not existing.get("deleted_at"):

            connection.close()

            return api_error(
                "Este movimiento no está eliminado.",
                400
            )

        # ====================================================
        # RESTAURAR
        # ====================================================

        cursor.execute(
            """
            UPDATE movements
            SET
                deleted_at = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (
                now_iso(),
                movement_id
            )
        )

        connection.commit()

        # Obtener movimiento restaurado.

        cursor.execute(
            """
            SELECT *
            FROM movements
            WHERE id = ?
            LIMIT 1
            """,
            (movement_id,)
        )

        restored_row = cursor.fetchone()

        connection.close()

        restored = normalize_movement(
            row_to_dict(restored_row)
        )

        return jsonify({
            "ok": True,
            "movement": restored
        })

    except Exception as error:

        print(
            "ERROR restaurando movimiento:",
            error
        )

        return api_error(
            "Error interno restaurando el movimiento.",
            500
        )


# ============================================================
# API — RESUMEN FINANCIERO
# ============================================================

@app.route(
    "/api/summary",
    methods=["GET"]
)
def summary():

    try:

        connection = get_db()
        cursor = connection.cursor()

        # ====================================================
        # INGRESOS
        # ====================================================

        cursor.execute(
            """
            SELECT COALESCE(
                SUM(amount),
                0
            ) AS total
            FROM movements
            WHERE
                type = 'ingreso'
                AND deleted_at IS NULL
            """
        )

        ingresos = Decimal(
            str(
                cursor.fetchone()["total"]
            )
        )

        # ====================================================
        # GASTOS
        # ====================================================

        cursor.execute(
            """
            SELECT COALESCE(
                SUM(amount),
                0
            ) AS total
            FROM movements
            WHERE
                type = 'gasto'
                AND deleted_at IS NULL
            """
        )

        gastos = Decimal(
            str(
                cursor.fetchone()["total"]
            )
        )

        connection.close()

        # ====================================================
        # SALDO
        # ====================================================

        saldo = ingresos - gastos

        return jsonify({
            "ok": True,
            "ingresos": float(ingresos),
            "gastos": float(gastos),
            "saldo": float(saldo)
        })

    except Exception as error:

        print(
            "ERROR calculando resumen:",
            error
        )

        return api_error(
            "Error interno calculando el resumen.",
            500
        )


# ============================================================
# MANEJADOR DE ERRORES 404 PARA API
# ============================================================

@app.errorhandler(404)
def not_found(error):

    if request.path.startswith("/api/"):

        return jsonify({
            "ok": False,
            "error": "Endpoint no encontrado."
        }), 404

    return error


# ============================================================
# MANEJADOR DE ERRORES 500
# ============================================================

@app.errorhandler(500)
def internal_error(error):

    if request.path.startswith("/api/"):

        return jsonify({
            "ok": False,
            "error": "Error interno del servidor."
        }), 500

    return error


# ============================================================
# EJECUTAR
# ============================================================

if __name__ == "__main__":

    # Crear base de datos automáticamente.
    init_db()

    print()
    print("==============================================")
    print(" TESORERÍA — IGLESIA CATÓLICA LOS ARRAYANES")
    print("==============================================")

    print(
        "Base de datos:",
        "SQLite"
    )

    print(
        "Archivo:",
        DB_PATH
    )

    print(
        "Usuario administrador:",
        ADMIN_USERNAME
    )

    print("==============================================")
    print()

    port = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
