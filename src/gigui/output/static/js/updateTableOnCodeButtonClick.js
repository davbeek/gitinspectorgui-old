// Add event listeners to the buttons in the Code column of the blame tables to update
// the visibility of rows based on the state of the buttons:
// .blame-exclusions-button, .blame-empty-lines-button, and .hide-colors-button

document.addEventListener("DOMContentLoaded", function () {

    // Update the visibility of rows based on the state of the buttons:
    const updateRows = () => {
        document.querySelectorAll('table').forEach(table => {
            // Use global variables for button states
            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const codeCell = row.querySelector('.code-col');
                const firstCell = row.cells[0];
                const secondCell = row.cells[1];
                const isEmptyLine = codeCell && codeCell.textContent.trim() === '';
                const isExcludedAuthor = firstCell && secondCell && firstCell.textContent.trim() === '0' && !secondCell.textContent.includes('*');

                // isExclusionsPressed and isEmptyLinesPressed are globally declared in
                // globals.js
                row.style.display = (isExcludedAuthor && isExclusionsPressed)
                    || (isEmptyLine && isEmptyLinesPressed) ? 'none' : '';

                // isHideColorsPressed is globally declared in globals.js
                if (isHideColorsPressed) {
                    row.classList.add('hide-colors');
                } else {
                    row.classList.remove('hide-colors');
                }
            });
        });
    };

    const updateButtonStates = () => {
        document.querySelectorAll('.blame-exclusions-button').forEach(button => {
            button.classList.toggle('pressed', isExclusionsPressed);
        });
        document.querySelectorAll('.blame-empty-lines-button').forEach(button => {
            button.classList.toggle('pressed', isEmptyLinesPressed);
        });
        document.querySelectorAll('.hide-colors-button').forEach(button => {
            button.classList.toggle('pressed', isHideColorsPressed);
        });
    };

    const addEventListenersToButtons = () => {
        document.querySelectorAll('.blame-empty-lines-button, .blame-exclusions-button, .hide-colors-button').forEach(button => {
            if (!button.classList.contains('hide-colors-button')) {
                // Set initial state based on the presence of the 'pressed' class
                updateRows()
            };

            button.onclick = function () {
                // Store the current scroll position as a relative value
                const storeY = window.scrollY / document.documentElement.scrollHeight;

                // Toggle the value of the global variables instead of toggling the 'pressed' class
                if (button.classList.contains('blame-exclusions-button')) {
                    isExclusionsPressed = !isExclusionsPressed;
                } else if (button.classList.contains('blame-empty-lines-button')) {
                    isEmptyLinesPressed = !isEmptyLinesPressed;
                } else if (button.classList.contains('hide-colors-button')) {
                    isHideColorsPressed = !isHideColorsPressed;
                }
                updateRows();
                updateButtonStates();

                // Restore the scroll position as a relative value
                window.scrollTo({ top: storeY * document.documentElement.scrollHeight, behavior: 'instant' });
            };
        });
    };

    // Use MutationObserver to watch for changes in the DOM and add event listeners to the buttons
    const observer = new MutationObserver((mutationsList) => {
        for (const mutation of mutationsList) {
            if (mutation.type === 'childList') {
                addEventListenersToButtons();
                updateButtonStates(); // Ensure new buttons have the correct initial state
            }
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });

    // Initial call to add event listeners to existing buttons and update their states
    addEventListenersToButtons();
    updateRows(); // Ensure rows are updated based on the initial state
    updateButtonStates(); // Ensure buttons have the correct initial state
});
