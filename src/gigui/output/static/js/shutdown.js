// This script sends a beacon request to the server when the browser is closed
// Used only for dynamic blame history

window.addEventListener("beforeunload", function (event) {
    const port = window.location.port;
    const url = `http://localhost:${port}/shutdown?id=${browserId}`; // Include the browser ID in the URL
    const data = new Blob([], { type: "application/x-www-form-urlencoded" });
    navigator.sendBeacon(url, data);
});
