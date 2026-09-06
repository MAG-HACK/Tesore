import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)

# ============================================================
# CONFIGURACIÓN
# ============================================================

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "change-this-secret-key-in-render"
)

app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 7
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# En Render usamos HTTPS.
if os.environ.get("RENDER") == "true":
    app.config["SESSION_COOKIE_SECURE"] = True

DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


# ============================================================
# CONEXIÓN A SUPABASE
# ============================================================

def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL no está configurada. "
            "Agrega la variable DATABASE_URL en Render."
        )

    database_url = DATABASE_URL

    # Supabase requiere conexión SSL.
    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url += f"{separator}sslmode=require"

    return psycopg2.connect(database_url)


# ============================================================
# UTILIDADES
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def is_admin():
    return session.get("admin_logged_in") is True


def require_admin():
    if not is_admin():
        return jsonify({
            "ok": False,
            "error": "No autorizado"
        }), 401

    return None


def movement_to_dict(row):
    if not row:
        return None

    result = dict(row)

    if isinstance(result.get("amount"), Decimal):
        result["amount"] = float(result["amount"])

    for field in ["created_at", "updated_at", "deleted_at"]:
        if result.get(field) is not None:
            result[field] = result[field].isoformat()

    if result.get("date") is not None:
        result["date"] = result["date"].isoformat()

    return result


def get_json_data():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return None

    return data


def validate_movement_data(data):
    if not data:
        return "No se recibieron datos."

    movement_type = str(data.get("type", "")).strip().lower()
    amount_value = data.get("amount")
    description = str(data.get("description", "")).strip()
    date_value = str(data.get("date", "")).strip()
    category = str(data.get("category", "")).strip()
    other_detail = str(data.get("other_detail", "")).strip()

    if movement_type not in ["income", "expense"]:
        return "El tipo debe ser income o expense."

    if amount_value is None or str(amount_value).strip() == "":
        return "El monto es obligatorio."

    try:
        amount = Decimal(str(amount_value))
    except (InvalidOperation, ValueError):
        return "El monto no es válido."

    if amount <= 0:
        return "El monto debe ser mayor que cero."

    if not description:
        return "La descripción es obligatoria."

    if not date_value:
        return "La fecha es obligatoria."

    try:
        datetime.strptime(date_value, "%Y-%m-%d")
    except ValueError:
        return "La fecha debe tener el formato YYYY-MM-DD."

    if not category:
        return "La categoría es obligatoria."

    if category.lower() == "otros" and not other_detail:
        return "Debes especificar el detalle de 'Otros'."

    return None


# ============================================================
# CREACIÓN / VERIFICACIÓN DE TABLAS
# ============================================================

def init_database():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS movements (
                    id SERIAL PRIMARY KEY,
                    type VARCHAR(20) NOT NULL,
                    amount NUMERIC(12, 2) NOT NULL,
                    description TEXT NOT NULL,
                    date DATE NOT NULL,
                    category VARCHAR(100) NOT NULL,
                    other_detail TEXT,
                    deleted_at TIMESTAMPTZ NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cursor.execute("""
                SELECT id
                FROM admin
                WHERE username = %s
                LIMIT 1;
            """, (ADMIN_USERNAME,))

            admin_exists = cursor.fetchone()

            if not admin_exists:
                hashed_password = generate_password_hash(ADMIN_PASSWORD)

                cursor.execute("""
                    INSERT INTO admin (
                        username,
                        password
                    )
                    VALUES (%s, %s);
                """, (
                    ADMIN_USERNAME,
                    hashed_password
                ))

            connection.commit()

    finally:
        connection.close()


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():
    try:
        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
        finally:
            connection.close()

        return jsonify({
            "ok": True,
            "database": "connected"
        })

    except Exception as error:
        return jsonify({
            "ok": False,
            "database": "error",
            "error": str(error)
        }), 500


# ============================================================
# AUTENTICACIÓN
# ============================================================

@app.route("/api/auth/status", methods=["GET"])
def auth_status():
    return jsonify({
        "ok": True,
        "authenticated": is_admin(),
        "username": session.get("admin_username")
    })


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = get_json_data()

    if not data:
        return jsonify({
            "ok": False,
            "error": "Datos inválidos."
        }), 400

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if not username or not password:
        return jsonify({
            "ok": False,
            "error": "Usuario y contraseña son obligatorios."
        }), 400

    connection = get_db_connection()

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:

            cursor.execute("""
                SELECT id, username, password
                FROM admin
                WHERE username = %s
                LIMIT 1;
            """, (username,))

            admin = cursor.fetchone()

            if not admin:
                return jsonify({
                    "ok": False,
                    "error": "Usuario o contraseña incorrectos."
                }), 401

            stored_password = admin["password"]

            valid_password = False

            # Contraseñas nuevas almacenadas con Werkzeug.
            try:
                valid_password = check_password_hash(
                    stored_password,
                    password
                )
            except (ValueError, TypeError):
                valid_password = False

            # Compatibilidad con una contraseña antigua almacenada
            # como texto plano.
            if not valid_password and stored_password == password:
                valid_password = True

                new_hash = generate_password_hash(password)

                cursor.execute("""
                    UPDATE admin
                    SET password = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s;
                """, (
                    new_hash,
                    admin["id"]
                ))

                connection.commit()

            if not valid_password:
                return jsonify({
                    "ok": False,
                    "error": "Usuario o contraseña incorrectos."
                }), 401

            session.clear()
            session.permanent = True
            session["admin_logged_in"] = True
            session["admin_username"] = admin["username"]

            return jsonify({
                "ok": True,
                "authenticated": True,
                "username": admin["username"]
            })

    finally:
        connection.close()


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()

    return jsonify({
        "ok": True
    })


# ============================================================
# OBTENER MOVIMIENTOS
# ============================================================

@app.route("/api/movements", methods=["GET"])
def get_movements():
    include_deleted = (
        request.args.get("include_deleted", "false").lower() == "true"
    )

    try:
        limit = int(request.args.get("limit", 100))
    except ValueError:
        limit = 100

    try:
        offset = int(request.args.get("offset", 0))
    except ValueError:
        offset = 0

    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    connection = get_db_connection()

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:

            if include_deleted:
                auth_error = require_admin()

                if auth_error:
                    return auth_error

                cursor.execute("""
                    SELECT
                        id,
                        type,
                        amount,
                        description,
                        date,
                        category,
                        other_detail,
                        deleted_at,
                        created_at,
                        updated_at
                    FROM movements
                    ORDER BY date DESC, id DESC
                    LIMIT %s OFFSET %s;
                """, (
                    limit,
                    offset
                ))

            else:
                cursor.execute("""
                    SELECT
                        id,
                        type,
                        amount,
                        description,
                        date,
                        category,
                        other_detail,
                        deleted_at,
                        created_at,
                        updated_at
                    FROM movements
                    WHERE deleted_at IS NULL
                    ORDER BY date DESC, id DESC
                    LIMIT %s OFFSET %s;
                """, (
                    limit,
                    offset
                ))

            rows = cursor.fetchall()

            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM movements
                WHERE deleted_at IS NULL;
            """)

            total = cursor.fetchone()["total"]

            return jsonify({
                "ok": True,
                "movements": [
                    movement_to_dict(row)
                    for row in rows
                ],
                "total": total,
                "limit": limit,
                "offset": offset
            })

    finally:
        connection.close()


# ============================================================
# OBTENER UN MOVIMIENTO
# ============================================================

@app.route("/api/movements/<int:movement_id>", methods=["GET"])
def get_movement(movement_id):
    connection = get_db_connection()

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:

            cursor.execute("""
                SELECT
                    id,
                    type,
                    amount,
                    description,
                    date,
                    category,
                    other_detail,
                    deleted_at,
                    created_at,
                    updated_at
                FROM movements
                WHERE id = %s
                LIMIT 1;
            """, (movement_id,))

            row = cursor.fetchone()

            if not row:
                return jsonify({
                    "ok": False,
                    "error": "Movimiento no encontrado."
                }), 404

            return jsonify({
                "ok": True,
                "movement": movement_to_dict(row)
            })

    finally:
        connection.close()


# ============================================================
# CREAR MOVIMIENTO
# ============================================================

@app.route("/api/movements", methods=["POST"])
def create_movement():
    auth_error = require_admin()

    if auth_error:
        return auth_error

    data = get_json_data()

    validation_error = validate_movement_data(data)

    if validation_error:
        return jsonify({
            "ok": False,
            "error": validation_error
        }), 400

    movement_type = str(data["type"]).strip().lower()
    amount = Decimal(str(data["amount"]))
    description = str(data["description"]).strip()
    date_value = str(data["date"]).strip()
    category = str(data["category"]).strip()
    other_detail = str(data.get("other_detail", "")).strip()

    if category.lower() != "otros":
        other_detail = None

    connection = get_db_connection()

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:

            cursor.execute("""
                INSERT INTO movements (
                    type,
                    amount,
                    description,
                    date,
                    category,
                    other_detail
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING
                    id,
                    type,
                    amount,
                    description,
                    date,
                    category,
                    other_detail,
                    deleted_at,
                    created_at,
                    updated_at;
            """, (
                movement_type,
                amount,
                description,
                date_value,
                category,
                other_detail
            ))

            movement = cursor.fetchone()

            connection.commit()

            return jsonify({
                "ok": True,
                "movement": movement_to_dict(movement)
            }), 201

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ============================================================
# EDITAR MOVIMIENTO
# ============================================================

@app.route("/api/movements/<int:movement_id>", methods=["PUT"])
def update_movement(movement_id):
    auth_error = require_admin()

    if auth_error:
        return auth_error

    data = get_json_data()

    validation_error = validate_movement_data(data)

    if validation_error:
        return jsonify({
            "ok": False,
            "error": validation_error
        }), 400

    movement_type = str(data["type"]).strip().lower()
    amount = Decimal(str(data["amount"]))
    description = str(data["description"]).strip()
    date_value = str(data["date"]).strip()
    category = str(data["category"]).strip()
    other_detail = str(data.get("other_detail", "")).strip()

    if category.lower() != "otros":
        other_detail = None

    connection = get_db_connection()

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:

            cursor.execute("""
                SELECT id
                FROM movements
                WHERE id = %s
                LIMIT 1;
            """, (movement_id,))

            existing = cursor.fetchone()

            if not existing:
                return jsonify({
                    "ok": False,
                    "error": "Movimiento no encontrado."
                }), 404

            cursor.execute("""
                UPDATE movements
                SET
                    type = %s,
                    amount = %s,
                    description = %s,
                    date = %s,
                    category = %s,
                    other_detail = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING
                    id,
                    type,
                    amount,
                    description,
                    date,
                    category,
                    other_detail,
                    deleted_at,
                    created_at,
                    updated_at;
            """, (
                movement_type,
                amount,
                description,
                date_value,
                category,
                other_detail,
                movement_id
            ))

            movement = cursor.fetchone()

            connection.commit()

            return jsonify({
                "ok": True,
                "movement": movement_to_dict(movement)
            })

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ============================================================
# ELIMINACIÓN LÓGICA
# ============================================================

@app.route("/api/movements/<int:movement_id>", methods=["DELETE"])
def delete_movement(movement_id):
    auth_error = require_admin()

    if auth_error:
        return auth_error

    connection = get_db_connection()

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:

            cursor.execute("""
                SELECT id, deleted_at
                FROM movements
                WHERE id = %s
                LIMIT 1;
            """, (movement_id,))

            movement = cursor.fetchone()

            if not movement:
                return jsonify({
                    "ok": False,
                    "error": "Movimiento no encontrado."
                }), 404

            if movement["deleted_at"] is not None:
                return jsonify({
                    "ok": False,
                    "error": "El movimiento ya está eliminado."
                }), 400

            cursor.execute("""
                UPDATE movements
                SET
                    deleted_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING
                    id,
                    type,
                    amount,
                    description,
                    date,
                    category,
                    other_detail,
                    deleted_at,
                    created_at,
                    updated_at;
            """, (movement_id,))

            deleted_movement = cursor.fetchone()

            connection.commit()

            return jsonify({
                "ok": True,
                "message": "Movimiento eliminado correctamente.",
                "movement": movement_to_dict(deleted_movement)
            })

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ============================================================
# HISTORIAL DE MOVIMIENTOS ELIMINADOS
# ============================================================

@app.route("/api/admin/history", methods=["GET"])
def admin_history():
    auth_error = require_admin()

    if auth_error:
        return auth_error

    connection = get_db_connection()

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:

            cursor.execute("""
                SELECT
                    id,
                    type,
                    amount,
                    description,
                    date,
                    category,
                    other_detail,
                    deleted_at,
                    created_at,
                    updated_at
                FROM movements
                WHERE deleted_at IS NOT NULL
                ORDER BY deleted_at DESC, id DESC;
            """)

            rows = cursor.fetchall()

            return jsonify({
                "ok": True,
                "movements": [
                    movement_to_dict(row)
                    for row in rows
                ],
                "total": len(rows)
            })

    finally:
        connection.close()


# ============================================================
# RESTAURAR MOVIMIENTO
# ============================================================

@app.route("/api/movements/<int:movement_id>/restore", methods=["POST"])
def restore_movement(movement_id):
    auth_error = require_admin()

    if auth_error:
        return auth_error

    connection = get_db_connection()

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:

            cursor.execute("""
                SELECT id, deleted_at
                FROM movements
                WHERE id = %s
                LIMIT 1;
            """, (movement_id,))

            movement = cursor.fetchone()

            if not movement:
                return jsonify({
                    "ok": False,
                    "error": "Movimiento no encontrado."
                }), 404

            if movement["deleted_at"] is None:
                return jsonify({
                    "ok": False,
                    "error": "El movimiento ya está activo."
                }), 400

            cursor.execute("""
                UPDATE movements
                SET
                    deleted_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING
                    id,
                    type,
                    amount,
                    description,
                    date,
                    category,
                    other_detail,
                    deleted_at,
                    created_at,
                    updated_at;
            """, (movement_id,))

            restored_movement = cursor.fetchone()

            connection.commit()

            return jsonify({
                "ok": True,
                "message": "Movimiento restaurado correctamente.",
                "movement": movement_to_dict(restored_movement)
            })

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ============================================================
# ELIMINACIÓN PERMANENTE
# ============================================================

@app.route(
    "/api/movements/<int:movement_id>/permanent",
    methods=["DELETE"]
)
def permanent_delete_movement(movement_id):
    auth_error = require_admin()

    if auth_error:
        return auth_error

    connection = get_db_connection()

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:

            cursor.execute("""
                SELECT
                    id,
                    deleted_at
                FROM movements
                WHERE id = %s
                LIMIT 1;
            """, (movement_id,))

            movement = cursor.fetchone()

            if not movement:
                return jsonify({
                    "ok": False,
                    "error": "Movimiento no encontrado."
                }), 404

            # Solo se puede eliminar permanentemente algo
            # que ya fue enviado a la papelera.
            if movement["deleted_at"] is None:
                return jsonify({
                    "ok": False,
                    "error": (
                        "Primero debes eliminar lógicamente "
                        "el movimiento."
                    )
                }), 400

            cursor.execute("""
                DELETE FROM movements
                WHERE id = %s
                RETURNING id;
            """, (movement_id,))

            deleted = cursor.fetchone()

            connection.commit()

            return jsonify({
                "ok": True,
                "message": "Movimiento eliminado permanentemente.",
                "id": deleted["id"]
            })

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ============================================================
# RESUMEN / BALANCE
# ============================================================

@app.route("/api/summary", methods=["GET"])
def summary():
    connection = get_db_connection()

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:

            cursor.execute("""
                SELECT
                    COALESCE(
                        SUM(
                            CASE
                                WHEN type = 'income'
                                THEN amount
                                ELSE 0
                            END
                        ),
                        0
                    ) AS income,

                    COALESCE(
                        SUM(
                            CASE
                                WHEN type = 'expense'
                                THEN amount
                                ELSE 0
                            END
                        ),
                        0
                    ) AS expenses,

                    COUNT(*) AS total_movements

                FROM movements
                WHERE deleted_at IS NULL;
            """)

            result = cursor.fetchone()

            income = Decimal(result["income"] or 0)
            expenses = Decimal(result["expenses"] or 0)
            balance = income - expenses

            return jsonify({
                "ok": True,
                "income": float(income),
                "expenses": float(expenses),
                "balance": float(balance),
                "total_movements": result["total_movements"]
            })

    finally:
        connection.close()


# ============================================================
# MANEJO DE ERRORES
# ============================================================

@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({
            "ok": False,
            "error": "Recurso no encontrado."
        }), 404

    return render_template("index.html"), 404


@app.errorhandler(500)
def internal_error(error):
    if request.path.startswith("/api/"):
        return jsonify({
            "ok": False,
            "error": "Error interno del servidor."
        }), 500

    return "Error interno del servidor.", 500


# ============================================================
# INICIALIZACIÓN
# ============================================================

if __name__ == "__main__":
    try:
        init_database()
        print("Base de datos conectada correctamente.")
    except Exception as error:
        print("Error conectando con la base de datos:")
        print(error)

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )