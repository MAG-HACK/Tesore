/* ============================================================
   TESORERÍA — IGLESIA CATÓLICA DE LOS ARRAYANES
   APP.JS COMPLETO
   ============================================================ */

"use strict";

/* ============================================================
   ESTADO
   ============================================================ */

let isAdmin = false;
let editingId = null;
let deletingId = null;
let currentPage = 0;
let currentLimit = 10;
let showingAll = false;
let showingDeletedHistory = false;

/* ============================================================
   ELEMENTOS
   ============================================================ */

const $ = (id) => document.getElementById(id);

/* ============================================================
   UTILIDADES
   ============================================================ */

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatMoney(value) {
    const number = Number(value || 0);

    return number.toLocaleString("es-HN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function formatDate(value) {
    if (!value) {
        return "";
    }

    const parts = String(value).split("-");

    if (parts.length === 3) {
        return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }

    return value;
}

function showToast(message, type = "success") {
    const toast = $("toast");

    if (!toast) {
        return;
    }

    toast.textContent = message;
    toast.className = `toast ${type}`;

    clearTimeout(showToast.timeout);

    showToast.timeout = setTimeout(() => {
        toast.className = "toast";
        toast.textContent = "";
    }, 3500);
}

async function apiRequest(url, options = {}) {
    const finalOptions = {
        credentials: "same-origin",
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        }
    };

    const response = await fetch(url, finalOptions);

    let data = {};

    try {
        data = await response.json();
    } catch (error) {
        data = {};
    }

    if (!response.ok || data.ok === false) {
        const message =
            data.error ||
            data.message ||
            `Error HTTP ${response.status}`;

        const error = new Error(message);
        error.status = response.status;
        error.data = data;

        throw error;
    }

    return data;
}

/* ============================================================
   AUTENTICACIÓN
   ============================================================ */

async function checkAuth() {
    try {
        const data = await apiRequest("/api/auth/status");

        isAdmin = Boolean(data.authenticated);

        updateAdminUI();

        if (isAdmin) {
            createDeletedHistoryUI();
        } else {
            removeDeletedHistoryUI();
        }

        await loadMovements();
        await loadSummary();

        if (isAdmin) {
            await loadDeletedHistory();
        }
    } catch (error) {
        console.error("Error comprobando autenticación:", error);

        isAdmin = false;

        updateAdminUI();
        removeDeletedHistoryUI();

        await loadMovements();
        await loadSummary();
    }
}

function updateAdminUI() {
    const loginBtn = $("loginBtn");
    const logoutBtn = $("logoutBtn");
    const adminStatus = $("adminStatus");
    const adminPanel = $("adminPanel");
    const actionsHeader = $("actionsHeader");

    if (isAdmin) {
        if (loginBtn) {
            loginBtn.classList.add("hidden");
        }

        if (logoutBtn) {
            logoutBtn.classList.remove("hidden");
        }

        if (adminStatus) {
            adminStatus.classList.remove("hidden");
        }

        if (adminPanel) {
            adminPanel.classList.remove("hidden");
        }

        if (actionsHeader) {
            actionsHeader.classList.remove("hidden");
        }
    } else {
        if (loginBtn) {
            loginBtn.classList.remove("hidden");
        }

        if (logoutBtn) {
            logoutBtn.classList.add("hidden");
        }

        if (adminStatus) {
            adminStatus.classList.add("hidden");
        }

        if (adminPanel) {
            adminPanel.classList.add("hidden");
        }

        if (actionsHeader) {
            actionsHeader.classList.add("hidden");
        }
    }
}

/* ============================================================
   LOGIN
   ============================================================ */

function openLoginModal() {
    const modal = $("loginModal");

    if (!modal) {
        return;
    }

    modal.classList.remove("hidden");

    const password = $("password");

    if (password) {
        setTimeout(() => {
            password.focus();
        }, 50);
    }
}

function closeLoginModal() {
    const modal = $("loginModal");

    if (!modal) {
        return;
    }

    modal.classList.add("hidden");

    const password = $("password");
    const error = $("loginError");

    if (password) {
        password.value = "";
    }

    if (error) {
        error.textContent = "";
    }
}

async function handleLogin(event) {
    event.preventDefault();

    const password = $("password");
    const loginError = $("loginError");

    if (!password) {
        return;
    }

    const enteredPassword = password.value.trim();

    if (!enteredPassword) {
        if (loginError) {
            loginError.textContent = "Introduce la contraseña.";
        }

        return;
    }

    if (loginError) {
        loginError.textContent = "";
    }

    try {
        const data = await apiRequest("/api/auth/login", {
            method: "POST",
            body: JSON.stringify({
                username: "admin",
                password: enteredPassword
            })
        });

        if (data.ok) {
            isAdmin = true;

            closeLoginModal();
            updateAdminUI();

            createDeletedHistoryUI();

            await loadMovements();
            await loadSummary();
            await loadDeletedHistory();

            showToast("Sesión iniciada correctamente.");
        }
    } catch (error) {
        console.error("Error de login:", error);

        if (loginError) {
            loginError.textContent =
                error.message ||
                "Usuario o contraseña incorrectos.";
        }
    }
}

async function logout() {
    try {
        await apiRequest("/api/auth/logout", {
            method: "POST"
        });
    } catch (error) {
        console.error("Error cerrando sesión:", error);
    }

    isAdmin = false;
    editingId = null;

    cancelEdit();

    closeLoginModal();

    removeDeletedHistoryUI();

    updateAdminUI();

    await loadMovements();
    await loadSummary();

    showToast("Sesión cerrada.");
}

/* ============================================================
   RESUMEN
   ============================================================ */

async function loadSummary() {
    try {
        const data = await apiRequest("/api/summary");

        if ($("saldo")) {
            $("saldo").textContent =
                `L ${formatMoney(data.saldo)}`;
        }

        if ($("ingresos")) {
            $("ingresos").textContent =
                `L ${formatMoney(data.ingresos)}`;
        }

        if ($("gastos")) {
            $("gastos").textContent =
                `L ${formatMoney(data.gastos)}`;
        }
    } catch (error) {
        console.error("Error cargando resumen:", error);
    }
}

/* ============================================================
   FILTROS
   ============================================================ */

function getMovementFilters(includeDeleted = false) {
    const params = new URLSearchParams();

    const search = $("search");
    const from = $("from");
    const to = $("to");
    const filterType = $("filterType");
    const filterCategory = $("filterCategory");

    if (search && search.value.trim()) {
        params.set("search", search.value.trim());
    }

    if (from && from.value) {
        params.set("from", from.value);
    }

    if (to && to.value) {
        params.set("to", to.value);
    }

    if (
        filterType &&
        filterType.value
    ) {
        params.set("type", filterType.value);
    }

    if (
        filterCategory &&
        filterCategory.value
    ) {
        params.set("category", filterCategory.value);
    }

    if (includeDeleted) {
        params.set("deleted", "true");
    }

    return params;
}

/* ============================================================
   MOVIMIENTOS
   ============================================================ */

async function loadMovements() {
    const table = $("movementTable");
    const emptyState = $("emptyState");

    if (!table) {
        return;
    }

    table.innerHTML = `
        <tr>
            <td colspan="${isAdmin ? 6 : 5}" style="text-align:center;">
                Cargando movimientos...
            </td>
        </tr>
    `;

    try {
        const params = getMovementFilters(false);

        params.set(
            "limit",
            showingAll ? "500" : String(currentLimit)
        );

        params.set(
            "offset",
            showingAll ? "0" : String(currentPage * currentLimit)
        );

        const data = await apiRequest(
            `/api/movements?${params.toString()}`
        );

        renderMovements(data.movements || []);

        updateShowAllButton(data.total || 0);
    } catch (error) {
        console.error("Error cargando movimientos:", error);

        table.innerHTML = `
            <tr>
                <td colspan="${isAdmin ? 6 : 5}" style="text-align:center;">
                    No se pudieron cargar los movimientos.
                </td>
            </tr>
        `;

        if (emptyState) {
            emptyState.classList.add("hidden");
        }

        if (error.status === 401) {
            isAdmin = false;
            updateAdminUI();
            removeDeletedHistoryUI();
        }
    }
}

function renderMovements(movements) {
    const table = $("movementTable");
    const emptyState = $("emptyState");

    if (!table) {
        return;
    }

    table.innerHTML = "";

    if (!movements.length) {
        if (emptyState) {
            emptyState.classList.remove("hidden");
        }

        return;
    }

    if (emptyState) {
        emptyState.classList.add("hidden");
    }

    movements.forEach((movement) => {
        const row = document.createElement("tr");

        const typeClass =
            movement.type === "ingreso"
                ? "income"
                : "expense";

        const typeLabel =
            movement.type === "ingreso"
                ? "Ingreso"
                : "Gasto";

        const otherDetail =
            movement.category === "Otros" &&
            movement.other_detail
                ? `<br><small>${escapeHtml(movement.other_detail)}</small>`
                : "";

        row.innerHTML = `
            <td>
                ${escapeHtml(formatDate(movement.date))}
            </td>

            <td>
                <strong>
                    ${escapeHtml(movement.description)}
                </strong>
            </td>

            <td>
                ${escapeHtml(movement.category)}
                ${otherDetail}
            </td>

            <td>
                <span class="${typeClass}">
                    ${typeLabel}
                </span>
            </td>

            <td>
                <strong>
                    L ${formatMoney(movement.amount)}
                </strong>
            </td>

            ${
                isAdmin
                    ? `
                    <td class="admin-column">
                        <div class="movement-actions">

                            <button
                                type="button"
                                class="btn btn-secondary btn-small"
                                data-action="edit"
                                data-id="${movement.id}"
                            >
                                ✏️ Editar
                            </button>

                            <button
                                type="button"
                                class="btn btn-danger btn-small"
                                data-action="delete"
                                data-id="${movement.id}"
                            >
                                🗑️ Eliminar
                            </button>

                        </div>
                    </td>
                    `
                    : ""
            }
        `;

        table.appendChild(row);
    });

    bindMovementActions();
}

function bindMovementActions() {
    document
        .querySelectorAll(
            '[data-action="edit"]'
        )
        .forEach((button) => {
            button.addEventListener("click", () => {
                const id = Number(
                    button.dataset.id
                );

                editMovement(id);
            });
        });

    document
        .querySelectorAll(
            '[data-action="delete"]'
        )
        .forEach((button) => {
            button.addEventListener("click", () => {
                const id = Number(
                    button.dataset.id
                );

                openDeleteModal(id);
            });
        });
}

function updateShowAllButton(total) {
    const button = $("showAllBtn");

    if (!button) {
        return;
    }

    if (showingAll) {
        button.textContent = "Mostrar menos";
    } else {
        button.textContent =
            total > currentLimit
                ? "Mostrar todo"
                : "Mostrar todo";
    }
}

/* ============================================================
   EDITAR
   ============================================================ */

async function editMovement(id) {
    if (!isAdmin) {
        showToast(
            "Debes iniciar sesión como administrador.",
            "error"
        );

        return;
    }

    try {
        const data = await apiRequest(
            `/api/movements/${id}`
        );

        const movement = data.movement;

        if (!movement) {
            throw new Error(
                "Movimiento no encontrado."
            );
        }

        editingId = id;

        if ($("editId")) {
            $("editId").value = id;
        }

        if ($("type")) {
            $("type").value =
                movement.type || "ingreso";
        }

        if ($("amount")) {
            $("amount").value =
                movement.amount ?? "";
        }

        if ($("date")) {
            $("date").value =
                movement.date || "";
        }

        if ($("category")) {
            $("category").value =
                movement.category || "";
        }

        if ($("description")) {
            $("description").value =
                movement.description || "";
        }

        if ($("otherDetail")) {
            $("otherDetail").value =
                movement.other_detail || "";
        }

        updateOtherField();

        const saveBtn = $("saveBtn");
        const cancelBtn = $("cancelEditBtn");

        if (saveBtn) {
            saveBtn.textContent =
                "💾 Guardar cambios";
        }

        if (cancelBtn) {
            cancelBtn.classList.remove("hidden");
        }

        const adminPanel = $("adminPanel");

        if (adminPanel) {
            adminPanel.scrollIntoView({
                behavior: "smooth",
                block: "start"
            });
        }
    } catch (error) {
        console.error(
            "Error cargando movimiento:",
            error
        );

        showToast(
            error.message ||
                "No se pudo cargar el movimiento.",
            "error"
        );
    }
}

function cancelEdit() {
    editingId = null;

    if ($("editId")) {
        $("editId").value = "";
    }

    const form = $("movementForm");

    if (form) {
        form.reset();
    }

    updateOtherField();

    const saveBtn = $("saveBtn");
    const cancelBtn = $("cancelEditBtn");

    if (saveBtn) {
        saveBtn.textContent =
            "💾 Guardar movimiento";
    }

    if (cancelBtn) {
        cancelBtn.classList.add("hidden");
    }

    setDefaultDate();
}

async function handleMovementSubmit(event) {
    event.preventDefault();

    if (!isAdmin) {
        showToast(
            "Debes iniciar sesión como administrador.",
            "error"
        );

        return;
    }

    const type = $("type");
    const amount = $("amount");
    const date = $("date");
    const category = $("category");
    const description = $("description");
    const otherDetail = $("otherDetail");

    if (
        !type ||
        !amount ||
        !date ||
        !category ||
        !description
    ) {
        return;
    }

    const data = {
        type: type.value,
        amount: amount.value,
        date: date.value,
        category: category.value,
        description: description.value.trim(),
        other_detail:
            otherDetail
                ? otherDetail.value.trim()
                : ""
    };

    try {
        const url = editingId
            ? `/api/movements/${editingId}`
            : "/api/movements";

        const method = editingId
            ? "PUT"
            : "POST";

        await apiRequest(url, {
            method,
            body: JSON.stringify(data)
        });

        if (editingId) {
            showToast(
                "Movimiento actualizado correctamente."
            );
        } else {
            showToast(
                "Movimiento guardado correctamente."
            );
        }

        cancelEdit();

        showingAll = false;
        currentPage = 0;

        await loadMovements();
        await loadSummary();

        if (isAdmin) {
            await loadDeletedHistory();
        }
    } catch (error) {
        console.error(
            "Error guardando movimiento:",
            error
        );

        showToast(
            error.message ||
                "No se pudo guardar el movimiento.",
            "error"
        );
    }
}

/* ============================================================
   CAMPO OTROS
   ============================================================ */

function updateOtherField() {
    const category = $("category");
    const otherWrap = $("otherWrap");
    const otherDetail = $("otherDetail");

    if (!category || !otherWrap) {
        return;
    }

    if (category.value === "Otros") {
        otherWrap.classList.remove("hidden");

        if (otherDetail) {
            otherDetail.required = true;
        }
    } else {
        otherWrap.classList.add("hidden");

        if (otherDetail) {
            otherDetail.required = false;
            otherDetail.value = "";
        }
    }
}

function setDefaultDate() {
    const date = $("date");

    if (!date || date.value) {
        return;
    }

    const today = new Date();

    const year = today.getFullYear();
    const month = String(
        today.getMonth() + 1
    ).padStart(2, "0");

    const day = String(
        today.getDate()
    ).padStart(2, "0");

    date.value =
        `${year}-${month}-${day}`;
}

/* ============================================================
   ELIMINACIÓN NORMAL
   ============================================================ */

function openDeleteModal(id) {
    if (!isAdmin) {
        showToast(
            "Debes iniciar sesión como administrador.",
            "error"
        );

        return;
    }

    deletingId = Number(id);

    const modal = $("deleteModal");

    if (!modal) {
        return;
    }

    modal.classList.remove("hidden");
}

function closeDeleteModal() {
    deletingId = null;

    const modal = $("deleteModal");

    if (!modal) {
        return;
    }

    modal.classList.add("hidden");
}

async function confirmDelete() {
    if (!isAdmin) {
        closeDeleteModal();

        showToast(
            "No autorizado.",
            "error"
        );

        return;
    }

    if (!deletingId) {
        closeDeleteModal();

        return;
    }

    const id = deletingId;

    const button = $("confirmDeleteBtn");

    if (button) {
        button.disabled = true;
        button.textContent =
            "Eliminando...";
    }

    try {
        await apiRequest(
            `/api/movements/${id}`,
            {
                method: "DELETE"
            }
        );

        closeDeleteModal();

        showToast(
            "Movimiento eliminado y enviado al historial."
        );

        await loadMovements();
        await loadSummary();

        if (isAdmin) {
            await loadDeletedHistory();
        }
    } catch (error) {
        console.error(
            "Error eliminando movimiento:",
            error
        );

        showToast(
            error.message ||
                "No se pudo eliminar el movimiento.",
            "error"
        );
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent =
                "Sí, eliminar";
        }
    }
}

/* ============================================================
   HISTORIAL DE ELIMINADOS
   ============================================================ */

function createDeletedHistoryUI() {
    if (!isAdmin) {
        return;
    }

    if ($("deletedHistoryPanel")) {
        return;
    }

    const main = document.querySelector("main.container");

    if (!main) {
        return;
    }

    const section = document.createElement("section");

    section.id = "deletedHistoryPanel";
    section.className =
        "panel admin-panel";

   

    main.appendChild(section);

    const refreshBtn =
        $("refreshDeletedHistoryBtn");

    if (refreshBtn) {
        refreshBtn.addEventListener(
            "click",
            loadDeletedHistory
        );
    }
}

function removeDeletedHistoryUI() {
    const panel = $("deletedHistoryPanel");

    if (panel) {
        panel.remove();
    }

    showingDeletedHistory = false;
}

async function loadDeletedHistory() {
    if (!isAdmin) {
        return;
    }

    createDeletedHistoryUI();

    const table =
        $("deletedMovementTable");

    const emptyState =
        $("deletedEmptyState");

    if (!table) {
        return;
    }

    table.innerHTML = `
        <tr>
            <td colspan="7" style="text-align:center;">
                Cargando historial...
            </td>
        </tr>
    `;

    try {
        const data = await apiRequest(
            "/api/admin/history"
        );

        const movements =
            data.movements ||
            data.history ||
            data.deleted_movements ||
            [];

        renderDeletedHistory(movements);
    } catch (error) {
        console.error(
            "Error cargando historial:",
            error
        );

        table.innerHTML = `
            <tr>
                <td colspan="7" style="text-align:center;">
                    No se pudo cargar el historial.
                </td>
            </tr>
        `;

        if (emptyState) {
            emptyState.classList.add("hidden");
        }

        if (error.status === 401) {
            isAdmin = false;

            updateAdminUI();
            removeDeletedHistoryUI();
        }
    }
}

function renderDeletedHistory(movements) {
    const table =
        $("deletedMovementTable");

    const emptyState =
        $("deletedEmptyState");

    if (!table) {
        return;
    }

    table.innerHTML = "";

    if (!movements.length) {
        if (emptyState) {
            emptyState.classList.remove("hidden");
        }

        return;
    }

    if (emptyState) {
        emptyState.classList.add("hidden");
    }

    movements.forEach((movement) => {
        const row = document.createElement("tr");

        const typeLabel =
            movement.type === "ingreso"
                ? "Ingreso"
                : "Gasto";

        const deletedAt =
            formatDeletedDate(
                movement.deleted_at
            );

        const otherDetail =
            movement.category === "Otros" &&
            movement.other_detail
                ? `<br><small>${escapeHtml(movement.other_detail)}</small>`
                : "";

        row.innerHTML = `
            <td>
                ${escapeHtml(
                    formatDate(movement.date)
                )}
            </td>

            <td>
                <strong>
                    ${escapeHtml(
                        movement.description
                    )}
                </strong>
            </td>

            <td>
                ${escapeHtml(
                    movement.category
                )}

                ${otherDetail}
            </td>

            <td>
                ${typeLabel}
            </td>

            <td>
                <strong>
                    L ${formatMoney(
                        movement.amount
                    )}
                </strong>
            </td>

            <td>
                <small>
                    ${escapeHtml(deletedAt)}
                </small>
            </td>

            <td>
                <div class="movement-actions">

                    <button
                        type="button"
                        class="btn btn-secondary btn-small"
                        data-history-action="restore"
                        data-id="${movement.id}"
                    >
                        ♻️ Restaurar
                    </button>

                    <button
                        type="button"
                        class="btn btn-danger btn-small"
                        data-history-action="permanent"
                        data-id="${movement.id}"
                    >
                        🗑️ Borrar definitivamente
                    </button>

                </div>
            </td>
        `;

        table.appendChild(row);
    });

    bindHistoryActions();
}

function bindHistoryActions() {
    document
        .querySelectorAll(
            '[data-history-action="restore"]'
        )
        .forEach((button) => {
            button.addEventListener(
                "click",
                () => {
                    const id = Number(
                        button.dataset.id
                    );

                    restoreMovement(id);
                }
            );
        });

    document
        .querySelectorAll(
            '[data-history-action="permanent"]'
        )
        .forEach((button) => {
            button.addEventListener(
                "click",
                () => {
                    const id = Number(
                        button.dataset.id
                    );

                    permanentDeleteMovement(id);
                }
            );
        });
}

/* ============================================================
   RESTAURAR
   ============================================================ */

async function restoreMovement(id) {
    if (!isAdmin) {
        showToast(
            "No autorizado.",
            "error"
        );

        return;
    }

    const confirmed = window.confirm(
        "¿Quieres restaurar este movimiento?\n\n" +
        "Volverá a aparecer entre los movimientos activos " +
        "y volverá a afectar el saldo."
    );

    if (!confirmed) {
        return;
    }

    try {
        await apiRequest(
            `/api/movements/${id}/restore`,
            {
                method: "POST"
            }
        );

        showToast(
            "Movimiento restaurado correctamente."
        );

        await loadMovements();
        await loadSummary();
        await loadDeletedHistory();
    } catch (error) {
        console.error(
            "Error restaurando movimiento:",
            error
        );

        showToast(
            error.message ||
                "No se pudo restaurar el movimiento.",
            "error"
        );
    }
}

/* ============================================================
   BORRAR DEFINITIVAMENTE
   ============================================================ */

async function permanentDeleteMovement(id) {
    if (!isAdmin) {
        showToast(
            "No autorizado.",
            "error"
        );

        return;
    }

    const confirmed = window.confirm(
        "⚠️ ATENCIÓN\n\n" +
        "Este movimiento será BORRADO DEFINITIVAMENTE " +
        "de la base de datos.\n\n" +
        "Después de hacerlo NO podrá restaurarse.\n\n" +
        "¿Estás completamente seguro?"
    );

    if (!confirmed) {
        return;
    }

    const secondConfirmation = window.prompt(
        "Para confirmar el borrado definitivo escribe:\n\n" +
        "BORRAR"
    );

    if (secondConfirmation !== "BORRAR") {
        showToast(
            "Borrado definitivo cancelado.",
            "error"
        );

        return;
    }

    const buttons =
        document.querySelectorAll(
            `[data-history-action="permanent"][data-id="${id}"]`
        );

    buttons.forEach((button) => {
        button.disabled = true;
        button.textContent =
            "Borrando...";
    });

    try {
        /*
         * ESTA ES LA LLAMADA IMPORTANTE.
         *
         * El backend Flask tiene esta ruta:
         *
         * DELETE /api/movements/<id>/permanent
         *
         * Aquí hacemos exactamente esa petición.
         */

        const data = await apiRequest(
            `/api/movements/${id}/permanent`,
            {
                method: "DELETE"
            }
        );

        if (!data.ok) {
            throw new Error(
                data.error ||
                    "No se pudo borrar definitivamente."
            );
        }

        showToast(
            "Movimiento borrado definitivamente."
        );

        await loadDeletedHistory();
        await loadMovements();
        await loadSummary();
    } catch (error) {
        console.error(
            "ERROR BORRANDO DEFINITIVAMENTE:",
            error
        );

        showToast(
            error.message ||
                "No se pudo borrar definitivamente el movimiento.",
            "error"
        );

        buttons.forEach((button) => {
            button.disabled = false;
            button.textContent =
                "🗑️ Borrar definitivamente";
        });
    }
}

function formatDeletedDate(value) {
    if (!value) {
        return "—";
    }

    try {
        const date = new Date(value);

        if (Number.isNaN(date.getTime())) {
            return String(value);
        }

        return date.toLocaleString("es-HN", {
            dateStyle: "short",
            timeStyle: "short"
        });
    } catch (error) {
        return String(value);
    }
}

/* ============================================================
   MOSTRAR TODO
   ============================================================ */

function toggleShowAll() {
    showingAll = !showingAll;

    currentPage = 0;

    loadMovements();
}

/* ============================================================
   FILTROS
   ============================================================ */

function applyFilters() {
    currentPage = 0;
    showingAll = false;

    loadMovements();
}

function clearFilters() {
    if ($("search")) {
        $("search").value = "";
    }

    if ($("from")) {
        $("from").value = "";
    }

    if ($("to")) {
        $("to").value = "";
    }

    if ($("filterType")) {
        $("filterType").value = "";
    }

    if ($("filterCategory")) {
        $("filterCategory").value = "";
    }

    currentPage = 0;
    showingAll = false;

    loadMovements();
}

/* ============================================================
   EVENTOS
   ============================================================ */

function setupEvents() {
    const loginBtn = $("loginBtn");

    if (loginBtn) {
        loginBtn.addEventListener(
            "click",
            openLoginModal
        );
    }

    const logoutBtn = $("logoutBtn");

    if (logoutBtn) {
        logoutBtn.addEventListener(
            "click",
            logout
        );
    }

    const closeModal = $("closeModal");

    if (closeModal) {
        closeModal.addEventListener(
            "click",
            closeLoginModal
        );
    }

    const loginModal = $("loginModal");

    if (loginModal) {
        loginModal.addEventListener(
            "click",
            (event) => {
                if (
                    event.target ===
                    loginModal
                ) {
                    closeLoginModal();
                }
            }
        );
    }

    const loginForm = $("loginForm");

    if (loginForm) {
        loginForm.addEventListener(
            "submit",
            handleLogin
        );
    }

    const movementForm =
        $("movementForm");

    if (movementForm) {
        movementForm.addEventListener(
            "submit",
            handleMovementSubmit
        );
    }

    const cancelEditBtn =
        $("cancelEditBtn");

    if (cancelEditBtn) {
        cancelEditBtn.addEventListener(
            "click",
            cancelEdit
        );
    }

    const category =
        $("category");

    if (category) {
        category.addEventListener(
            "change",
            updateOtherField
        );
    }

    const cancelDeleteBtn =
        $("cancelDeleteBtn");

    if (cancelDeleteBtn) {
        cancelDeleteBtn.addEventListener(
            "click",
            closeDeleteModal
        );
    }

    const confirmDeleteBtn =
        $("confirmDeleteBtn");

    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener(
            "click",
            confirmDelete
        );
    }

    const deleteModal =
        $("deleteModal");

    if (deleteModal) {
        deleteModal.addEventListener(
            "click",
            (event) => {
                if (
                    event.target ===
                    deleteModal
                ) {
                    closeDeleteModal();
                }
            }
        );
    }

    const filterBtn =
        $("filterBtn");

    if (filterBtn) {
        filterBtn.addEventListener(
            "click",
            applyFilters
        );
    }

    const showAllBtn =
        $("showAllBtn");

    if (showAllBtn) {
        showAllBtn.addEventListener(
            "click",
            toggleShowAll
        );
    }

    const search =
        $("search");

    if (search) {
        search.addEventListener(
            "keydown",
            (event) => {
                if (event.key === "Enter") {
                    event.preventDefault();
                    applyFilters();
                }
            }
        );
    }

    document.addEventListener(
        "keydown",
        (event) => {
            if (event.key !== "Escape") {
                return;
            }

            closeLoginModal();
            closeDeleteModal();
        }
    );
}

/* ============================================================
   INICIO
   ============================================================ */

document.addEventListener(
    "DOMContentLoaded",
    async () => {
        setupEvents();

        setDefaultDate();
        updateOtherField();

        await checkAuth();
    }
);