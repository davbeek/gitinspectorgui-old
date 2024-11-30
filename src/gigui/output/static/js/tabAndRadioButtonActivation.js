// Add event listeners for tab activation and radio button clicks
document.addEventListener("DOMContentLoaded", function () {
    // Function to click the first radio button in the active tab
    function clickFirstRadioButton(tabContent) {
        const firstRadioButton = tabContent.querySelector('input[type="radio"]');
        if (firstRadioButton) {
            firstRadioButton.click();
        }
    }

    // Add event listener for tab activation
    const tabs = document.querySelectorAll('.nav-link[data-bs-toggle="tab"]');
    const activatedTabs = new Set();

    tabs.forEach(tab => {
        tab.addEventListener('shown.bs.tab', function (event) {
            const targetId = event.target.getAttribute('data-bs-target');
            const tabContent = document.querySelector(targetId);

            if (!activatedTabs.has(targetId)) {
                clickFirstRadioButton(tabContent);
                activatedTabs.add(targetId);
            }

            // Adjust the position of the radio button row for the active tab
            const radioButtonRow = tabContent.querySelector('.radio-container');
            if (radioButtonRow) {
                radioButtonRow.style.position = 'sticky';
                radioButtonRow.style.top = tabRow.offsetHeight + 'px';
            }
        });
    });

    // Initial click for the first radio button in the initially active tab
    const initialActiveTab = document.querySelector('.nav-link.active');
    if (initialActiveTab) {
        const initialTargetId = initialActiveTab.getAttribute('data-bs-target');
        const initialTabContent = document.querySelector(initialTargetId);
        clickFirstRadioButton(initialTabContent);
        activatedTabs.add(initialTargetId);
    }

    // Add event listener for radio button clicks in each blame-container
    var blameContainers = document.querySelectorAll('.blame-container');
    var storeY = 0;
    blameContainers.forEach(function (blameContainer) {
        var radioButtons = blameContainer.querySelectorAll('.radio-button');
        var tableContainer = blameContainer.querySelector('.table-container');
        radioButtons.forEach(function (radioButton) {
            radioButton.addEventListener('click', function () {
                // Store the current scroll position as a relative value
                storeY = window.scrollY / document.documentElement.scrollHeight;

                // Hide all tables in the .table-container
                tableContainer.querySelectorAll('table').forEach(table => table.style.display = 'none');

                // Check if the table is already in the DOM using its table id
                const tableId = radioButton.id.replace('button-', '');
                const existingTable = tableContainer.querySelector(`table#${tableId}`);

                // <%= browser_id %> will be replaced with the actual browser ID
                const browserId = '<%= browser_id %>';

                if (existingTable) {
                    // Show the existing table
                    existingTable.style.display = '';
                    adjustHeaderRowPosition(existingTable);
                    // Restore the scroll position as a relative value
                    window.scrollTo({ top: storeY * document.documentElement.scrollHeight, behavior: 'instant' });
                } else {
                    // Fetch and insert the table if not already in the DOM
                    fetch(`/load-table/${tableId}?id=${browserId}`)
                        .then(response => response.text())
                        .then(html => {
                            const tempDiv = document.createElement('div');
                            tempDiv.innerHTML = html;
                            const table = tempDiv.querySelector('table');
                            table.id = tableId; // Ensure the table has the correct id
                            tableContainer.appendChild(table);
                            adjustHeaderRowPosition(table);
                            // Restore the scroll position as a relative value
                            window.scrollTo({ top: storeY * document.documentElement.scrollHeight, behavior: 'instant' });
                        })
                        .catch(error => console.error('Error loading table:', error));
                }
            });
        });
    });

    function adjustHeaderRowPosition(table) {
        const tabRow = document.getElementById('tabRow');
        const tabRowHeight = tabRow.offsetHeight;
        const radioButtonRow = table.closest('.tab-pane').querySelector('.radio-container');
        const radioButtonRowHeight = radioButtonRow ? radioButtonRow.offsetHeight : 0;
        const headerRow = table.querySelector('.headerRow');

        if (headerRow) {
            headerRow.style.position = 'sticky';
            headerRow.style.top = (tabRowHeight + radioButtonRowHeight) + 'px';
        }
    }
});
