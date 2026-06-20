// Sermon inline editing functions
function editSermon(sermonId) {
    // Hide all other edit forms
    document.querySelectorAll('.sermon-edit-row').forEach(row => {
        row.style.display = 'none';
    });
    document.querySelectorAll('.sermon-row').forEach(row => {
        row.style.display = '';
    });

    // Show edit form for this sermon
    const displayRow = document.querySelector(`tr[data-sermon-id="${sermonId}"]`);
    const editRow = document.getElementById(`edit-${sermonId}`);

    if (displayRow && editRow) {
        displayRow.style.display = 'none';
        editRow.style.display = '';
    }
}

function cancelEdit(sermonId) {
    const displayRow = document.querySelector(`tr[data-sermon-id="${sermonId}"]`);
    const editRow = document.getElementById(`edit-${sermonId}`);

    if (displayRow && editRow) {
        displayRow.style.display = '';
        editRow.style.display = 'none';
    }
}

// Shorts inline editing functions
function editShorts(shortsId) {
    document.querySelectorAll('.shorts-edit-row').forEach(row => {
        row.style.display = 'none';
    });
    document.querySelectorAll('.shorts-row').forEach(row => {
        row.style.display = '';
    });

    const displayRow = document.querySelector(`tr[data-shorts-id="${shortsId}"]`);
    const editRow = document.getElementById(`shorts-edit-${shortsId}`);

    if (displayRow && editRow) {
        displayRow.style.display = 'none';
        editRow.style.display = '';
    }
}

function cancelEditShorts(shortsId) {
    const displayRow = document.querySelector(`tr[data-shorts-id="${shortsId}"]`);
    const editRow = document.getElementById(`shorts-edit-${shortsId}`);

    if (displayRow && editRow) {
        displayRow.style.display = '';
        editRow.style.display = 'none';
    }
}

// QT inline editing functions
function editQty(qtyId) {
    document.querySelectorAll('.qty-edit-row').forEach(row => {
        row.style.display = 'none';
    });
    document.querySelectorAll('.qty-row').forEach(row => {
        row.style.display = '';
    });

    const displayRow = document.querySelector(`tr[data-qty-id="${qtyId}"]`);
    const editRow = document.getElementById(`qty-edit-${qtyId}`);

    if (displayRow && editRow) {
        displayRow.style.display = 'none';
        editRow.style.display = '';
    }
}

function cancelEditQty(qtyId) {
    const displayRow = document.querySelector(`tr[data-qty-id="${qtyId}"]`);
    const editRow = document.getElementById(`qty-edit-${qtyId}`);

    if (displayRow && editRow) {
        displayRow.style.display = '';
        editRow.style.display = 'none';
    }
}
