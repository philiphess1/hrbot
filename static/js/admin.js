let fileArray = []; // this will hold the selected files
document.addEventListener('DOMContentLoaded', (event) => {
    // Simulate a click on the chatbot button to open it when the page loads
    document.getElementById('chatbot-button').click();
});


document.getElementById("upload-form").addEventListener("submit", function(event) {
    event.preventDefault();
    uploadFiles();
});

function uploadFiles() {
    document.getElementById("form-content").style.display = "none";  // Hide form content
    document.getElementById("url-form").style.display = "none";  // Hide URL form
    document.getElementById("filelist").style.display = "none";  // Hide URL form
    document.getElementById("loading").style.display = "block";  // Show loading icon
    let formData = new FormData();

    for (let i = 0; i < fileArray.length; i++) {
        formData.append("file", fileArray[i]);
        formData.append("fileSize", fileArray[i].size);
    }

    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById("loading").style.display = "none";  // Hide loading icon
        document.getElementById("form-content").style.display = "block";  // Show form content
        if (data.status === "success") {
            // Redirect to the admin page
            window.location.href = '/admin';  
        } else {
            // Handle errors or show an error message to the user
            console.error(data.message);
        }
    })
    .catch(error => {
        document.getElementById("loading").style.display = "none";  // Hide loading icon
        document.getElementById("form-content").style.display = "block";  // Show form content
        console.error('There was an error!', error);
    });
}

document.getElementById('url-form').addEventListener('submit', function () {
    // Show loader_1 and hide url-area when form is submitted
    document.getElementById('url-area').style.display = 'none';
    document.getElementById('upload-form').style.display = 'none';
    document.getElementById('loading_1').style.display = 'flex';
});

document.getElementById("file").addEventListener("change", function() {
    const fileList = document.getElementById("file-list");
    fileList.innerHTML = ""; // clear current file list
    
    // Add newly selected files to fileArray
    for (let i = 0; i < this.files.length; i++) {
        fileArray.push(this.files[i]);
    }

    updateFileListDisplay();
});

function updateFileListDisplay() {
    const fileList = document.getElementById("filelist");
    fileList.innerHTML = ""; // clear current file list

    if (fileArray.length > 0) {
        fileList.style.display = "block";
    } else {
        fileList.style.display = "none";
    }

    let totalSize = 0; // Initialize total size

    // Update displayed file list
    for (let i = 0; i < fileArray.length; i++) {
        const fileSize = (fileArray[i].size / 1024 / 1024).toFixed(2); // Convert to MB and round to 2 decimal places
        totalSize += parseFloat(fileSize); // Add file size to total size
        const fileExtension = fileArray[i].name.split('.').pop().toLowerCase();
        let fileIcon = 'default';
        if (fileExtension.includes('xls')) {
            fileIcon = 'xlsx';
        } else if (fileExtension.includes('doc')) {
            fileIcon = 'docx';
        } else if (fileExtension === 'pdf') {
            fileIcon = 'pdf';
        } else if (fileExtension === 'csv') {
            fileIcon = 'csv';
        }
        let filename = fileArray[i].name;
            if (filename.length > 50) {
                filename = filename.substring(0, 25) + '...' + filename.substring(filename.length - 20);
            }

            const fileHtml = `
                <div id="fileitem">
                    <div id="fileinfo">
                        <img src="static/images/${fileIcon}.png" height="30" width="30" alt="PDF-icon">
                        <div id="filename">${filename}</div>
                        <div id="spacer"></div>
                        <div class="x-icon">
                            <img src="static/images/X-icon.png" height="20" width="20" alt="X-icon" class="remove-button" data-index="${i}">
                        </div>
                    </div>
                </div>
            `;

        // Insert the fileHtml into the DOM
        fileList.insertAdjacentHTML('beforeend', fileHtml);
    }

    // Attach event listeners after all elements are added to the DOM
    const removeButtons = document.querySelectorAll('.remove-button');
    removeButtons.forEach((button) => {
        button.addEventListener('click', function () {
            const index = this.getAttribute('data-index');
            totalSize -= parseFloat(fileArray[index].size / 1024 / 1024);
            fileArray.splice(index, 1);
            updateFileListDisplay();
            // update the file count display
            document.getElementById('file-label').innerHTML = fileArray.length + ' file(s) selected, total size: ' + totalSize.toFixed(2) + ' MB';
        });
    });

    if (fileArray.length === 0) {
        document.getElementById('uploading').style.display = 'none';
    }
}



document.getElementById('file').addEventListener('change', function() {
    if (this.files.length > 0) {
        document.getElementById('uploading').style.display = 'block';
    } else {
        document.getElementById('uploading').style.display = 'none';
    }
});

// After files are processed and removed from fileArray

let uploadArea = document.getElementById('upload-area');

uploadArea.addEventListener('dragenter', function() {
    uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', function() {
    uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('dragover', function(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
});

uploadArea.addEventListener('drop', function(event) {
    event.preventDefault();
    uploadArea.classList.remove('dragover');
    let files = event.dataTransfer.files;
    for (let i = 0; i < files.length; i++) {
        fileArray.push(files[i]);
    }
    document.getElementById("file").files = files;
    updateFileListDisplay();
    updateFileSizeAndCount();
});


function updateFileSizeAndCount() {
    var fileInput = document.getElementById('file');
    var totalSize = 0;
    for (var i = 0; i < fileInput.files.length; i++) {
        totalSize += fileInput.files[i].size;
    }
    // Convert the total size to megabytes
    totalSize = totalSize / 1024 / 1024;

    document.getElementById('file-label').innerHTML = fileInput.files.length + ' file(s) selected, total size: ' + totalSize.toFixed(2) + ' MB';

    if (totalSize > 10) {
        alert('The total size of all files must be less than 10 MB.');
        fileInput.value = '';
    }
}

// sidebar JS

/* Set the width of the sidebar to 250px (show it) */
function openNav() {
    document.getElementById("mySidepanel").style.width = "250px";
  }
  
  /* Set the width of the sidebar to 0 (hide it) */
  function closeNav() {
    document.getElementById("mySidepanel").style.width = "0";
  }

//   search bar JS
// Get current page URL
var url = window.location.pathname;

// Get the last part of the URL (after the last '/')
var page = url.substring(url.lastIndexOf('/') + 1);

// Remove the '.html' extension if it exists
if (page.endsWith('.html')) {
    page = page.substring(0, page.length - 5);
}

// Get all links
var links = document.getElementsByClassName('mgn-top');

// Get all buttons
var btns = document.getElementsByClassName('btns');

// Loop through all links
for (var i = 0; i < links.length; i++) {
    // Get the id of the link
    var id = links[i].id;

    // If the id is the same as the page
    if (id === page) {
        // Change the background color of the link
        links[i].style.color = 'white';
    }
}

// Get all buttons
var btns = document.getElementsByClassName('btns');

// Loop through all buttons
for (var i = 0; i < btns.length; i++) {
    // Get the id of the button
    var id = btns[i].id;

    // If the id is the same as the page
    if (id === page) {
        // Change the background color of the button
        btns[i].style.backgroundColor = '#444';
    }
}

function validateURL(url) {
    // Regular expression pattern for URL validation
    var pattern = new RegExp(
        "^" +
        // Protocol (optional)
        "(?:(?:https?|ftp):\\/\\/)?" +
        // Domain name (required)
        "(?:\\w+(?:\\.\\w+)+)" +
        // Optional port number
        "(?::\\d+)?" +
        // Optional path
        "(?:\\/[^\\s]*)?" +
        // Optional query string
        "(?:\\?[^\\s]*)?" +
        // Optional fragment identifier
        "(?:#[\\w\\-]*)?" +
        "$", "i");

    return pattern.test(url);
}

document.getElementById('url').addEventListener('input', function() {
    var url = this.value;
    document.getElementById('submit-button').disabled = !url || !validateURL(url);
});