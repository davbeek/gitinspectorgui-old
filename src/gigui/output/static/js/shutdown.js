window.addEventListener('beforeunload', function () {
    // Dynamically determine the port number from the current URL
    const port = window.location.port;
    console.log(`Attempting to send shutdown request to port: ${port}`);
    // Make an HTTP request to the custom endpoint to trigger send_terminate_token
    const url = `http://localhost:${port}/shutdown`;
    const data = new Blob([], { type: 'application/x-www-form-urlencoded' });
    navigator.sendBeacon(url, data);
});
