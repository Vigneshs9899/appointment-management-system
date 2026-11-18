/**
 * ==============================================================================
 * SHAYURE AYURVEDA — CLINICAL PORTAL FRONTEND ENGINE
 * Impeccable Healthcare UX • AJAX Intakes • Chart.js Theming • Toast Utility
 * ==============================================================================
 */

// ------------------------------------------------------------------------------
// 1. GLOBAL TOAST NOTIFICATION UTILITY
// ------------------------------------------------------------------------------
function showToast(message, type = 'success', duration = 5000) {
  let container = document.getElementById('toastContainer');
  if (!container) {
    let outerContainer = document.querySelector('.ayur-toast-container');
    if (!outerContainer) {
      outerContainer = document.createElement('div');
      outerContainer.className = 'position-fixed top-0 end-0 p-3 ayur-toast-container';
      outerContainer.style.zIndex = '1090';
      document.body.appendChild(outerContainer);
    }
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    outerContainer.appendChild(container);
  }

  const iconMap = {
    success: 'bi-check-circle-fill text-success',
    danger: 'bi-exclamation-triangle-fill text-danger',
    error: 'bi-exclamation-triangle-fill text-danger',
    warning: 'bi-exclamation-circle-fill text-warning',
    info: 'bi-info-circle-fill text-info'
  };

  const borderMap = {
    success: 'toast-ayur-success',
    danger: 'toast-ayur-danger',
    error: 'toast-ayur-danger',
    warning: 'toast-ayur-warning',
    info: 'toast-ayur-info'
  };

  const iconClass = iconMap[type] || iconMap.info;
  const borderClass = borderMap[type] || 'toast-ayur-info';
  const toastId = 'toast_' + Date.now();

  const toastEl = document.createElement('div');
  toastEl.id = toastId;
  toastEl.className = `toast ayur-toast show align-items-center mb-2 shadow ${borderClass}`;
  toastEl.setAttribute('role', 'alert');
  toastEl.setAttribute('aria-live', 'assertive');
  toastEl.setAttribute('aria-atomic', 'true');
  toastEl.setAttribute('data-bs-delay', duration.toString());
  toastEl.setAttribute('data-bs-autohide', 'true');

  toastEl.innerHTML = `
    <div class="d-flex align-items-center w-100">
      <div class="toast-body d-flex align-items-center gap-2">
        <i class="bi ${iconClass} fs-5 flex-shrink-0"></i>
        <span class="ayur-toast-msg">${message}</span>
      </div>
      <button type="button" class="btn-close me-3 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
  `;

  container.appendChild(toastEl);

  if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
    const bsToast = new bootstrap.Toast(toastEl, { delay: duration, autohide: true });
    bsToast.show();
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
  } else {
    setTimeout(() => {
      toastEl.classList.remove('show');
      setTimeout(() => toastEl.remove(), 400);
    }, duration);
  }
}

// Global aliases for swappability
window.showToast = showToast;
window.showAyurToast = showToast;


// ------------------------------------------------------------------------------
// 2. PATIENT DASHBOARD LOGIC (load, book, remove, edit)
// ------------------------------------------------------------------------------

/**
 * Load appointments for Patient Dashboard
 */
async function load() {
  const list = document.getElementById("list");
  if (!list) return; // Not on patient dashboard

  const searchInput = document.getElementById("search");
  const search = searchInput ? encodeURIComponent(searchInput.value.trim()) : "";

  list.innerHTML = `
    <li class="p-4 text-center text-muted">
      <div class="spinner-border spinner-border-sm text-success me-2" role="status"></div>
      Loading your consultations...
    </li>
  `;

  try {
    const res = await fetch(`/appointments?search=${search}`);
    if (!res.ok) {
      if (res.status === 401) {
        list.innerHTML = `<li class="p-4 text-center text-muted">Please <a href="/login" class="text-success fw-bold">sign in</a> to view your appointments.</li>`;
        return;
      }
      throw new Error(`Server returned ${res.status}`);
    }

    const data = await res.json();
    list.innerHTML = "";

    // Update patient dashboard counters
    const statTotalEl = document.getElementById("statTotalCount");
    const statConfirmedEl = document.getElementById("statConfirmedCount");
    if (statTotalEl) statTotalEl.textContent = data.length;
    if (statConfirmedEl) {
      const confirmedCount = data.filter(a => a.status === 'Confirmed' || a.status === 'Completed').length;
      statConfirmedEl.textContent = confirmedCount;
    }

    if (!data || data.length === 0) {
      list.innerHTML = `
        <li class="text-center py-5 px-3">
          <div class="display-6 mb-2">🌿</div>
          <h6 class="fw-bold text-muted mb-1">No Consultations Scheduled</h6>
          <p class="small text-muted mb-3">You do not have any appointments yet. Use the booking form on the left to schedule your first Ayurvedic intake.</p>
        </li>
      `;
      return;
    }

    data.forEach((a) => {
      let badgeClass = "badge-status-pending";
      let statusIcon = "bi-hourglass-split";

      if (a.status === "Confirmed") {
        badgeClass = "badge-status-confirmed";
        statusIcon = "bi-check-circle-fill";
      } else if (a.status === "Completed") {
        badgeClass = "badge-status-completed";
        statusIcon = "bi-check-all";
      } else if (a.status === "Cancelled") {
        badgeClass = "badge-status-cancelled";
        statusIcon = "bi-x-circle-fill";
      }

      // Format appointment time nicely
      let formattedTime = a.appointment_time || "Scheduled Soon";
      try {
        if (a.appointment_time) {
          const dateObj = new Date(a.appointment_time);
          if (!isNaN(dateObj.getTime())) {
            formattedTime = dateObj.toLocaleDateString('en-US', {
              weekday: 'short',
              month: 'short',
              day: 'numeric',
              year: 'numeric',
              hour: '2-digit',
              minute: '2-digit'
            });
          }
        }
      } catch (err) {
        // Fallback to raw string
      }

      const li = document.createElement("li");
      li.className = "appointment-card";
      li.setAttribute("data-status", a.status || "Pending");
      li.setAttribute("data-id", a.id);

      li.innerHTML = `
        <div class="d-flex flex-column flex-md-row justify-content-between align-items-md-start gap-3">
          <div class="d-flex align-items-start gap-3">
            <div class="appointment-avatar">
              <i class="bi bi-heart-pulse"></i>
            </div>
            <div>
              <div class="d-flex align-items-center gap-2 mb-1">
                <h6 class="fw-bold mb-0 text-dark">${a.doctor || "Ayurvedic Vaidya"}</h6>
                <span class="badge ${badgeClass}">
                  <i class="bi ${statusIcon} me-1"></i>${a.status || "Pending"}
                </span>
              </div>
              <div class="small text-muted mb-1">
                <i class="bi bi-person me-1"></i> Patient: <strong>${a.name}</strong> • <span class="text-secondary">Ref #SAY-${a.id}</span>
              </div>
              <div class="small text-muted">
                <i class="bi bi-calendar-event me-1 text-success"></i> Slot: <strong>${formattedTime}</strong>
              </div>
            </div>
          </div>

          <div class="d-flex flex-wrap gap-1 align-self-start mt-2 mt-md-0">
            <a href="/report/${a.id}" class="btn btn-sm btn-ayur-primary shadow-xs" title="View Full Medical Report & Prescription">
              <i class="bi bi-file-earmark-medical me-1"></i> Report
            </a>
            <button class="btn btn-sm btn-light" onclick="openEditModal(${a.id}, '${escapeHtml(a.name)}', '${escapeHtml(a.doctor)}', '${a.appointment_time}')" title="Reschedule Consultation">
              <i class="bi bi-pencil me-1"></i> Edit
            </button>
            <button class="btn btn-sm btn-outline-danger" onclick="remove(${a.id})" title="Cancel Consultation">
              <i class="bi bi-trash"></i>
            </button>
          </div>
        </div>

        ${a.symptoms ? `
          <div class="appointment-symptoms-quote">
            <i class="bi bi-chat-left-quote me-1 text-success"></i> <strong>Symptoms:</strong> ${escapeHtml(a.symptoms)}
          </div>
        ` : ''}
      `;

      list.appendChild(li);
    });
  } catch (e) {
    console.error("Failed to load appointments:", e);
    list.innerHTML = `
      <li class="p-4 text-center text-danger">
        <i class="bi bi-exclamation-triangle-fill me-2"></i> Failed to retrieve appointments. Please try refreshing.
      </li>
    `;
  }
}

/**
 * Helper to escape HTML characters safely
 */
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/'/g, '&#39;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/**
 * Book appointment on Patient Dashboard
 */
async function book() {
  const nameInput = document.getElementById("name");
  const doctorInput = document.getElementById("doctor");
  const timeInput = document.getElementById("appointment_time");
  const symptomsInput = document.getElementById("symptoms");
  const statusDiv = document.getElementById("status");
  const bookBtn = document.getElementById("bookBtn");

  const name = nameInput ? nameInput.value.trim() : "";
  const doctor = doctorInput ? doctorInput.value.trim() : "";
  const symptoms = symptomsInput ? symptomsInput.value.trim() : "";
  let appointment_time = timeInput ? timeInput.value.trim() : "";

  // Check fallback if datetime-local was split into date + time slot
  if (!appointment_time) {
    const dateVal = document.getElementById("appointment_date")?.value;
    const slotVal = document.getElementById("appointment_time_slot")?.value;
    if (dateVal && slotVal) {
      appointment_time = `${dateVal}T${slotVal}`;
    }
  }

  if (!name || !doctor || !appointment_time) {
    showToast("Please enter your name, select a doctor, and choose an appointment slot.", "warning");
    if (statusDiv) {
      statusDiv.innerHTML = '<div class="alert alert-warning py-2 small mb-3">Please fill in all required fields.</div>';
    }
    return;
  }

  // Set loading state
  if (bookBtn) {
    bookBtn.disabled = true;
    bookBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span> Scheduling...';
  }

  try {
    const response = await fetch("/appointments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name,
        doctor: doctor,
        appointment_time: appointment_time,
        symptoms: symptoms
      }),
    });

    if (response.ok) {
      showToast("Appointment booked successfully! Your Vaidya will review your intake.", "success");
      if (statusDiv) {
        statusDiv.innerHTML = '<div class="alert alert-success py-2 small mb-3">✓ Appointment booked successfully!</div>';
        setTimeout(() => { statusDiv.innerHTML = ''; }, 4000);
      }
      if (symptomsInput) symptomsInput.value = "";
      load();
    } else {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.message || err.error || "Failed to schedule appointment");
    }
  } catch (e) {
    console.error("Booking error:", e);
    showToast(`Booking failed: ${e.message}`, "danger");
    if (statusDiv) {
      statusDiv.innerHTML = `<div class="alert alert-danger py-2 small mb-3">Booking failed: ${e.message}</div>`;
    }
  } finally {
    if (bookBtn) {
      bookBtn.disabled = false;
      bookBtn.innerHTML = '<i class="bi bi-calendar2-check me-2"></i> Confirm & Book Appointment';
    }
  }
}

/**
 * Remove / Cancel appointment
 */
async function remove(id) {
  if (!confirm("Are you sure you wish to cancel this Ayurvedic consultation?")) {
    return;
  }

  try {
    const res = await fetch(`/appointments/${id}`, {
      method: "DELETE",
    });

    if (res.ok) {
      showToast("Consultation cancelled successfully.", "info");
      load();
    } else {
      throw new Error("Unable to cancel appointment.");
    }
  } catch (e) {
    console.error("Delete error:", e);
    showToast(`Error: ${e.message}`, "danger");
  }
}

/**
 * Open Edit Appointment Modal
 */
function openEditModal(id, currentName, currentDoctor, currentTime) {
  const modalEl = document.getElementById("editAppointmentModal");
  if (modalEl && typeof bootstrap !== 'undefined') {
    document.getElementById("editApptId").value = id;
    document.getElementById("editName").value = currentName || "";
    if (document.getElementById("editDoctor")) {
      document.getElementById("editDoctor").value = currentDoctor || "Dr. Shanmuga Loga";
    }
    if (document.getElementById("editTime")) {
      // Format to datetime-local
      if (currentTime && currentTime.includes("T")) {
        document.getElementById("editTime").value = currentTime.substring(0, 16);
      } else {
        document.getElementById("editTime").value = currentTime || "";
      }
    }
    const bsModal = new bootstrap.Modal(modalEl);
    bsModal.show();
  } else {
    // Fallback to prompts if modal isn't in DOM
    editAppointment(id, currentName, currentDoctor, currentTime);
  }
}

/**
 * Submit Edit from Modal
 */
async function submitEditAppointment() {
  const id = document.getElementById("editApptId").value;
  const newName = document.getElementById("editName").value.trim();
  const newDoctor = document.getElementById("editDoctor").value.trim();
  const newTime = document.getElementById("editTime").value;

  if (!newName || !newDoctor || !newTime) {
    showToast("Please provide all fields to update your consultation.", "warning");
    return;
  }

  try {
    const res = await fetch(`/appointments/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: newName,
        doctor: newDoctor,
        appointment_time: newTime,
      }),
    });

    if (res.ok) {
      showToast("Appointment details updated successfully!", "success");
      const modalEl = document.getElementById("editAppointmentModal");
      if (modalEl && typeof bootstrap !== 'undefined') {
        const modalInstance = bootstrap.Modal.getInstance(modalEl);
        if (modalInstance) modalInstance.hide();
      }
      load();
    } else {
      throw new Error("Failed to update appointment");
    }
  } catch (e) {
    showToast(`Update failed: ${e.message}`, "danger");
  }
}

/**
 * Legacy editAppointment fallback
 */
async function editAppointment(id, currentName, currentDoctor, currentTime) {
  const newName = prompt("Edit patient name:", currentName);
  if (newName === null) return;
  const newDoctor = prompt("Edit doctor name:", currentDoctor);
  if (newDoctor === null) return;
  const newTime = prompt("Edit appointment time (YYYY-MM-DDTHH:MM):", currentTime);
  if (newTime === null) return;

  if (!newName || !newDoctor || !newTime) return;

  try {
    await fetch(`/appointments/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: newName,
        doctor: newDoctor,
        appointment_time: newTime,
      }),
    });
    showToast("Consultation updated.", "success");
    load();
  } catch (e) {
    showToast("Failed to update consultation", "danger");
  }
}

/**
 * Change status helper
 */
async function changeStatus(id, targetStatus) {
  let status = targetStatus;
  if (!status) {
    status = prompt("Enter new status:\nPending\nConfirmed\nCompleted\nCancelled");
  }

  if (!status) return;

  try {
    const res = await fetch(`/appointments/${id}/status`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: status }),
    });

    if (res.ok) {
      showToast(`Appointment status updated to ${status}.`, "success");
      load();
    } else {
      throw new Error("Failed to update status");
    }
  } catch (e) {
    showToast(`Status change error: ${e.message}`, "danger");
  }
}


// ------------------------------------------------------------------------------
// 3. DOCTOR DASHBOARD AJAX INTAKE & TABLE INTERACTIONS
// ------------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", function () {
  
  // A. Auto-wire Add Patient Modal on Doctor Dashboard
  const addPatientForm = document.getElementById("addPatientForm");
  if (addPatientForm) {
    addPatientForm.addEventListener("submit", async function (e) {
      e.preventDefault();

      const btnSubmit = document.getElementById("btnSubmitPatient");
      const spinner = document.getElementById("patientSubmitSpinner");
      const submitText = document.getElementById("patientSubmitText");
      const modalAlert = document.getElementById("modalAlertBox");

      if (btnSubmit) btnSubmit.disabled = true;
      if (spinner) spinner.classList.remove("d-none");
      if (submitText) submitText.textContent = " Registering...";
      if (modalAlert) {
        modalAlert.className = "alert d-none mb-3";
      }

      const formData = new FormData(addPatientForm);
      const payload = {};
      formData.forEach((val, key) => { payload[key] = val; });

      try {
        // Attempt POST to /doctor/add-patient (or /api/doctor/patients)
        let response = await fetch("/doctor/add-patient", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json"
          },
          body: JSON.stringify(payload)
        });

        // If 404 or not json, try /api/doctor/patients
        if (response.status === 404) {
          response = await fetch("/api/doctor/patients", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Accept": "application/json"
            },
            body: JSON.stringify(payload)
          });
        }

        if (response.ok) {
          const resData = await response.json().catch(() => ({}));
          showToast(`✓ Patient ${payload.name} registered successfully!`, "success");

          if (modalAlert) {
            modalAlert.className = "alert alert-success mb-3";
            modalAlert.innerHTML = `<i class="bi bi-check-circle-fill me-2"></i> ${resData.message || "Patient registered successfully! Updating queue..."}`;
            modalAlert.classList.remove("d-none");
          }

          // Dynamically prepend new row into Doctor Dashboard table if available
          insertNewAppointmentRow(payload, resData.id || Date.now());

          // Hide modal via Bootstrap
          const modalEl = document.getElementById("addPatientModal");
          if (modalEl && typeof bootstrap !== 'undefined') {
            const bsModal = bootstrap.Modal.getInstance(modalEl);
            setTimeout(() => {
              if (bsModal) bsModal.hide();
              addPatientForm.reset();
              if (modalAlert) modalAlert.classList.add("d-none");
            }, 800);
          } else {
            setTimeout(() => window.location.reload(), 1000);
          }

        } else if (response.status === 405) {
          // Fall back to standard form submission
          addPatientForm.submit();
        } else {
          const err = await response.json().catch(() => ({}));
          throw new Error(err.error || err.message || `Server returned ${response.status}`);
        }

      } catch (err) {
        console.warn("AJAX add patient failed, submitting via form POST:", err);
        showToast(`Intake registered: ${err.message}`, "info");
        // Fallback standard post
        setTimeout(() => addPatientForm.submit(), 600);
      } finally {
        setTimeout(() => {
          if (btnSubmit) btnSubmit.disabled = false;
          if (spinner) spinner.classList.add("d-none");
          if (submitText) submitText.innerHTML = '<i class="bi bi-person-check-fill me-1"></i> Register & Schedule';
        }, 1200);
      }
    });
  }

  // B. Search & filter in table if patientSearchInput exists
  const tableSearchInput = document.getElementById("patientSearchInput");
  if (tableSearchInput) {
    tableSearchInput.addEventListener("input", function (e) {
      filterDoctorTable(e.target.value.trim().toLowerCase());
    });
  }
});

/**
 * Prepend a newly added patient row dynamically into doctor_dashboard table
 */
function insertNewAppointmentRow(payload, newId) {
  const tbody = document.getElementById("appointmentTableBody");
  if (!tbody) return;

  const emptyRow = document.getElementById("emptyTableRow");
  if (emptyRow) emptyRow.remove();

  const words = (payload.name || "Patient").split(" ");
  const init1 = words[0] ? words[0][0] : "P";
  const init2 = words[1] ? words[1][0] : "";
  const initials = (init1 + init2).toUpperCase();

  const tr = document.createElement("tr");
  tr.className = "appointment-row";
  tr.setAttribute("data-status", (payload.status || "Confirmed").toLowerCase());
  tr.setAttribute("data-name", (payload.name || "").toLowerCase());
  tr.setAttribute("data-doctor", (payload.doctor || "").toLowerCase());
  tr.setAttribute("data-id", newId);
  tr.style.backgroundColor = "rgba(216, 243, 220, 0.45)";

  tr.innerHTML = `
    <td>
      <div class="d-flex align-items-center gap-3">
        <div class="patient-avatar">${initials}</div>
        <div>
          <div class="fw-bold text-dark">${escapeHtml(payload.name)}</div>
          <div class="text-muted small">ID: #AYUR-${newId} • <span class="badge badge-dosha-tridosha">${escapeHtml(payload.dosha || 'Tridosha')}</span></div>
        </div>
      </div>
    </td>
    <td>
      <div class="d-flex align-items-center gap-2">
        <i class="bi bi-heart-pulse text-success"></i>
        <span class="fw-medium">${escapeHtml(payload.doctor || 'Dr. Shanmuga Loga')}</span>
      </div>
    </td>
    <td>
      <span class="fw-semibold">
        <i class="bi bi-calendar-event me-1 text-muted"></i>
        ${payload.appointment_time || 'Just Added'}
      </span>
    </td>
    <td>
      <span class="status-chip status-${(payload.status || 'Confirmed').toLowerCase()}" id="statusChip-${newId}">
        <i class="bi bi-check-circle-fill"></i> ${payload.status || 'Confirmed'}
      </span>
    </td>
    <td class="text-end">
      <div class="d-inline-flex align-items-center gap-2">
        <a href="/consultation/${newId}" class="btn-action-consult" title="Start Consultation">
          <i class="bi bi-clipboard2-pulse"></i>
          <span>Consult</span>
        </a>
        <a href="/report/${newId}" class="btn-action-report" title="View Clinical Report">
          <i class="bi bi-file-earmark-medical"></i>
          <span>Report</span>
        </a>
      </div>
    </td>
  `;

  tbody.insertBefore(tr, tbody.firstChild);

  // Fade back to normal background
  setTimeout(() => {
    tr.style.transition = "background-color 1.5s ease";
    tr.style.backgroundColor = "";
  }, 2500);

  // Update total badge
  const totalBadge = document.getElementById("tableTotalBadge");
  const rowCount = tbody.querySelectorAll(".appointment-row").length;
  if (totalBadge) {
    totalBadge.textContent = `${rowCount} Consultations`;
  }
}

/**
 * Filter Doctor Table
 */
function filterDoctorTable(query) {
  const rows = document.querySelectorAll(".appointment-row");
  const noResultsRow = document.getElementById("noSearchResultsRow");
  let visibleCount = 0;

  rows.forEach(r => {
    const text = r.innerText.toLowerCase();
    const name = (r.getAttribute("data-name") || "").toLowerCase();
    const doc = (r.getAttribute("data-doctor") || "").toLowerCase();

    if (!query || text.includes(query) || name.includes(query) || doc.includes(query)) {
      r.style.display = "";
      visibleCount++;
    } else {
      r.style.display = "none";
    }
  });

  if (noResultsRow) {
    if (visibleCount === 0 && rows.length > 0) {
      noResultsRow.classList.remove("d-none");
    } else {
      noResultsRow.classList.add("d-none");
    }
  }
}


// ------------------------------------------------------------------------------
// 4. CHART.JS BOTANICAL THEME & COLOR PALETTE DEFAULTS
// ------------------------------------------------------------------------------
if (typeof Chart !== 'undefined') {
  Chart.defaults.font.family = "'Plus Jakarta Sans', system-ui, sans-serif";
  Chart.defaults.color = "#526359";
  Chart.defaults.plugins.tooltip.backgroundColor = "#192a20";
  Chart.defaults.plugins.tooltip.titleFont = { family: "'Outfit', sans-serif", weight: 'bold' };
  Chart.defaults.plugins.tooltip.bodyFont = { family: "'Plus Jakarta Sans', sans-serif" };
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.displayColors = false;
}

// ------------------------------------------------------------------------------
// 5. INITIALIZATION HOOK
// ------------------------------------------------------------------------------
window.onload = function () {
  // If we are on the patient dashboard, load appointments
  if (document.getElementById("list")) {
    load();
  }
};
