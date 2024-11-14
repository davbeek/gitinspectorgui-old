window.addEventListener('beforeunload', function (event) {
    const port = window.location.port;
    const browserId = '<%= browser_id %>'; // This will be replaced with the actual browser ID
    const url = `http://localhost:${port}/shutdown?id=${browserId}`; // Include the browser ID in the URL

    const data = new Blob([], { type: 'application/x-www-form-urlencoded' });
    navigator.sendBeacon(url, data);
});
