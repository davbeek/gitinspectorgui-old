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
    blameContainers.forEach(function (blameContainer) {
        var radioButtons = blameContainer.querySelectorAll('.radio-button');
        var tableContainer = blameContainer.querySelector('.table-container');
        radioButtons.forEach(function (radioButton) {
            radioButton.addEventListener('click', function () {
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
                } else {
                    // Fetch and insert the table if not already in the DOM
                    console.log(`Fetching table with id: ${tableId}`);
                    fetch(`/load-table/${tableId}?id=${browserId}`)
                        .then(response => response.text())
                        .then(html => {
                            const tempDiv = document.createElement('div');
                            tempDiv.innerHTML = html;
                            const table = tempDiv.querySelector('table');
                            table.id = tableId; // Ensure the table has the correct id
                            tableContainer.appendChild(table);
                        })
                        .catch(error => console.error('Error loading table:', error));
                }
            });
        });
    });
});
