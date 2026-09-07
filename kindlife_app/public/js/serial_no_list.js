frappe.listview_settings['Serial No'] = {
    onload: function(listview) {
        setupBarcodeDownloadButton(listview);
    }
}


function setupBarcodeDownloadButton(listview) {
    // Add the "Download Barcodes" button to the page's "Actions" menu.
    listview.page.add_action_item(__('Download Barcodes'), () => {
        // 1.Click Button
        const checked_items = listview.get_checked_items(true);

        const download_url = '/api/method/kindlife_app.api.serial_no_list.generate_barcodes_for_serial_nos';
        
        // Create a form element
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = download_url;
        form.target = '_blank'; // This ensures the response opens in a new tab.

        // Create a hidden input to hold the data
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'selected_serials'; // Python will look for data with this name.
        input.value = JSON.stringify(checked_items); // Convert the JS array to a string.

        // Add the CSRF token for security
        // Frappe provides each user with a crpf toke, 
        // when it gets a request, it matches this token before processing the request
        const csrf_token_input = document.createElement('input');
        csrf_token_input.type = 'hidden';
        csrf_token_input.name = 'csrf_token';
        csrf_token_input.value = frappe.csrf_token;
        
        // Add the two hidden inputs to our invisible form.
        form.appendChild(input);
        form.appendChild(csrf_token_input);

        // Append the form to the body, submit it, and then remove it
        document.body.appendChild(form);
        //3. Make the api call to url with serial numbers
        form.submit();
        document.body.removeChild(form);
    });
}


