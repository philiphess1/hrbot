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
var links = document.getElementsByClassName('mgn');

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
