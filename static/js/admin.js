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

// 쌓인 목록 정리: 최근 항목 몇 개만 먼저 보여 주고, 검색칸과 "더 보기"로 나머지를 찾는다.
// 표(.admin-table)는 10줄, data-collapsible="N" 이 붙은 목록은 N개까지 먼저 보인다.
// 수정용 숨김 줄(*-edit-row)은 세지 않고 건드리지도 않는다.
(function () {
    function setupList(container, items, limit, label) {
        if (items.length <= limit) return;
        let expanded = false;
        const bar = document.createElement('div');
        bar.className = 'list-tools';
        const search = document.createElement('input');
        search.type = 'search';
        search.placeholder = label || '제목·날짜로 검색';
        const count = document.createElement('span');
        count.className = 'list-tools-count';
        bar.appendChild(search);
        bar.appendChild(count);
        const more = document.createElement('button');
        more.type = 'button';
        more.className = 'list-more-btn';

        function render() {
            const q = search.value.trim().toLowerCase();
            let shown = 0, matched = 0;
            items.forEach(function (el) {
                const hit = !q || el.textContent.toLowerCase().includes(q);
                if (hit) matched++;
                const visible = hit && (q || expanded || shown < limit);
                if (visible) shown++;
                el.classList.toggle('is-collapsed', !visible);
            });
            count.textContent = q ? `${matched}개 찾음` : `전체 ${items.length}개 중 ${shown}개 표시`;
            const hidden = q ? 0 : items.length - shown;
            more.style.display = hidden > 0 || (expanded && !q) ? '' : 'none';
            more.textContent = expanded ? '최근 항목만 보기' : `더 보기 (${hidden}개 더)`;
        }
        more.addEventListener('click', function () { expanded = !expanded; render(); });
        search.addEventListener('input', render);
        container.parentNode.insertBefore(bar, container);
        container.parentNode.insertBefore(more, container.nextSibling);
        render();
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('table.admin-table').forEach(function (table) {
            const rows = Array.from(table.querySelectorAll('tbody > tr'))
                .filter(function (tr) { return !/-edit-row\b/.test(tr.className); });
            setupList(table, rows, 10);
        });
        document.querySelectorAll('[data-collapsible]').forEach(function (box) {
            const limit = parseInt(box.getAttribute('data-collapsible'), 10) || 12;
            setupList(box, Array.from(box.children), limit, box.getAttribute('data-search-label'));
        });
    });
})();
