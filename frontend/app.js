const API_URL = "/api/patients";
const FIELDS = ["full_name", "dob", "email", "glucose", "haemoglobin", "cholesterol"];

const form = document.getElementById("patient-form");
const formTitle = document.getElementById("form-title");
const submitButton = document.getElementById("submit-button");
const cancelButton = document.getElementById("cancel-button");
const alertBox = document.getElementById("alert");
const tableBody = document.getElementById("patients-body");

let patients = [];
let editingId = null;

function showAlert(type, content) {
  alertBox.className = `alert alert-${type}`;
  alertBox.replaceChildren(content);
}

function hideAlert() {
  alertBox.className = "alert d-none";
  alertBox.replaceChildren();
}

function showSuccess(message) {
  showAlert("success", document.createTextNode(message));
}

function showErrors(errors) {
  const list = document.createElement("ul");
  list.className = "mb-0";
  for (const error of errors) {
    const item = document.createElement("li");
    item.textContent = error.message;
    list.appendChild(item);

    const input = form.elements[error.field];
    if (input) {
      input.classList.add("is-invalid");
    }
  }
  showAlert("danger", list);
}

function clearFieldHighlights() {
  for (const field of FIELDS) {
    form.elements[field].classList.remove("is-invalid");
  }
}

// The API returns errors as a list of {field, message}; anything else is shown as one general error.
async function readErrors(response) {
  try {
    const body = await response.json();
    if (Array.isArray(body.detail)) {
      return body.detail;
    }
  } catch {
    // The response had no JSON body; fall through to the general message.
  }
  return [{ field: "", message: `The request failed (HTTP ${response.status}).` }];
}

function setEditMode(patient) {
  editingId = patient.id;
  for (const field of FIELDS) {
    form.elements[field].value = patient[field];
  }
  formTitle.textContent = `Edit patient: ${patient.full_name}`;
  submitButton.textContent = "Update patient";
  cancelButton.classList.remove("d-none");
  hideAlert();
  clearFieldHighlights();
  form.scrollIntoView({ behavior: "smooth" });
}

function resetForm() {
  editingId = null;
  form.reset();
  formTitle.textContent = "Add patient";
  submitButton.textContent = "Add patient";
  cancelButton.classList.add("d-none");
  clearFieldHighlights();
}

function createCell(text) {
  const cell = document.createElement("td");
  // textContent, never innerHTML, so stored text can never run as HTML or script.
  cell.textContent = text;
  return cell;
}

function createActionButton(label, className, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `btn btn-sm ${className}`;
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function renderPatients() {
  if (patients.length === 0) {
    const row = document.createElement("tr");
    const cell = createCell("No patient records yet.");
    cell.colSpan = 9;
    cell.className = "text-center text-muted";
    row.appendChild(cell);
    tableBody.replaceChildren(row);
    return;
  }

  const rows = patients.map((patient, index) => {
    const row = document.createElement("tr");
    row.append(
      createCell(index + 1),
      createCell(patient.full_name),
      createCell(patient.dob),
      createCell(patient.email),
      createCell(patient.glucose),
      createCell(patient.haemoglobin),
      createCell(patient.cholesterol),
    );

    const remarksCell = createCell(patient.remarks ?? "");
    remarksCell.className = "remarks-cell";
    row.appendChild(remarksCell);

    const actionsCell = document.createElement("td");
    actionsCell.className = "text-nowrap";
    actionsCell.append(
      createActionButton("Edit", "btn-outline-primary me-1", () => setEditMode(patient)),
      createActionButton("Delete", "btn-outline-danger", () => deletePatient(patient)),
    );
    row.appendChild(actionsCell);
    return row;
  });
  tableBody.replaceChildren(...rows);
}

async function loadPatients() {
  try {
    const response = await fetch(API_URL);
    if (!response.ok) {
      showErrors(await readErrors(response));
      return;
    }
    patients = await response.json();
    renderPatients();
  } catch {
    showErrors([{ field: "", message: "Could not reach the server. Check that it is running." }]);
  }
}

async function savePatient(event) {
  event.preventDefault();
  hideAlert();
  clearFieldHighlights();

  const data = {};
  for (const field of FIELDS) {
    data[field] = form.elements[field].value;
  }
  const isEdit = editingId !== null;
  const url = isEdit ? `${API_URL}/${editingId}` : API_URL;

  submitButton.disabled = true;
  submitButton.textContent = "Analysing…";
  try {
    const response = await fetch(url, {
      method: isEdit ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      showErrors(await readErrors(response));
      return;
    }
    const saved = await response.json();
    resetForm();
    showSuccess(`${saved.full_name} was ${isEdit ? "updated" : "added"}.`);
    await loadPatients();
  } catch {
    showErrors([{ field: "", message: "Could not reach the server. Check that it is running." }]);
  } finally {
    submitButton.disabled = false;
    // After a successful save resetForm() has already switched back to Add mode.
    submitButton.textContent = editingId === null ? "Add patient" : "Update patient";
  }
}

async function deletePatient(patient) {
  if (!confirm(`Delete the record for ${patient.full_name}?`)) {
    return;
  }
  hideAlert();
  try {
    const response = await fetch(`${API_URL}/${patient.id}`, { method: "DELETE" });
    if (!response.ok) {
      showErrors(await readErrors(response));
      return;
    }
    if (editingId === patient.id) {
      resetForm();
    }
    showSuccess(`${patient.full_name} was deleted.`);
    await loadPatients();
  } catch {
    showErrors([{ field: "", message: "Could not reach the server. Check that it is running." }]);
  }
}

form.addEventListener("submit", savePatient);
cancelButton.addEventListener("click", () => {
  resetForm();
  hideAlert();
});

loadPatients();
