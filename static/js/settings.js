document.addEventListener('DOMContentLoaded', (event) => {
    const chatbotButton = document.getElementById('b');
    const mainContent = document.querySelector('.main-content');
    let isChatbotOpen = false;

    function updateChatbotState(isOpen) {
        if (mainContent.classList.contains('shifted') === isOpen) return; // Prevent unnecessary toggles
        isChatbotOpen = isOpen;
        mainContent.classList.toggle('shifted', isOpen);
        console.log('Chatbot is now:', isOpen ? 'open' : 'closed');
    }

    // Chatbot toggle button
    if (chatbotButton) {
        chatbotButton.addEventListener('click', function(event) {
            updateChatbotState(!isChatbotOpen);
        });
    } else {
        console.warn('Chatbot toggle button not found');
    }

    // Check for chatbot state changes
    const observeTarget = document.body;
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                const isChatbotVisible = document.body.classList.contains('cb-open');
                updateChatbotState(isChatbotVisible);
            }
        });
    });

    observer.observe(observeTarget, { attributes: true });

    // Automatically open the chatbot when the page loads
    setTimeout(() => {
        chatbotButton.click();
    }, 100);

    // Icon color change functionality
    var primaryInput = document.getElementById('primary');
    var secondaryInput = document.getElementById('secondary');

    primaryInput.addEventListener('input', function() {
        var primaries = document.querySelectorAll('.primary');
        primaries.forEach(function(primary) {
            primary.style.fill = this.value;
        }, this);
    });

    secondaryInput.addEventListener('input', function() {
        var secondaries = document.querySelectorAll('.secondary');
        secondaries.forEach(function(secondary) {
            secondary.style.fill = this.value;
        }, this);
    });

    // Trigger the input event manually
    primaryInput.dispatchEvent(new Event('input'));
    secondaryInput.dispatchEvent(new Event('input'));

    // Change display property
    var elementToDisplay = document.getElementById('svg_icon');
    elementToDisplay.style.display = 'block';

    // Form validation
    document.getElementById('settingsForm').addEventListener('submit', function(event) {
        var botTemperature = document.getElementById('bot_temperature').value;
        var customPrompt = document.getElementById('custom_prompt').value;
        var greetingMessage = document.getElementById('greeting_message').value;
        var chatbotTitle = document.getElementById('chatbot_title').value;

        if (!botTemperature || !customPrompt || !greetingMessage || !chatbotTitle) {
            alert('All fields must be filled out.');
            event.preventDefault();
        }

        if (botTemperature < 0 || botTemperature > 1) {
            alert('Bot Temperature must be between 0 and 1.');
            event.preventDefault();
        }

        if (customPrompt.length > 1000) {
            alert('Custom Prompt cannot be more than 1000 characters.');
            event.preventDefault();
        }

        if (greetingMessage.length > 250) {
            alert('Greeting Message cannot be more than 250 characters.');
            event.preventDefault();
        }

        if (chatbotTitle.length > 20) {
            alert('Chatbot Title cannot be more than 20 characters.');
            event.preventDefault();
        }
    });

    document.getElementById('bot_temperature').addEventListener('input', function() {
        document.getElementById('bot_temperature_value').textContent = this.value;
    });

    // FAQ functionality
    document.getElementById('add-premade-question').addEventListener('click', function() {
        var container = document.getElementById('premade-questions-container');
        var index = container.getElementsByClassName('premade-question').length + 1;
        var question = document.createElement('div');
        question.className = 'premade-question';
        question.innerHTML = `
            <label for="premade_question_${index}">Question:</label>
            <textarea id="premade_question_${index}" name="premade_questions[]" required></textarea>
            <label for="premade_response_${index}">Response:</label>
            <textarea id="premade_response_${index}" name="premade_responses[]" required></textarea>
            <button type="button" class="delete-premade-question">
                <i class="fas fa-trash"></i>
            </button>
        `;
        question.dataset.saved = 'false';
        container.appendChild(question);
    });

    document.getElementById('premade-questions-container').addEventListener('click', function(event) {
        var target = event.target;
        if (target.tagName !== 'BUTTON') {
            target = target.parentNode;
        }
        if (target.className === 'delete-premade-question') {
            if (target.parentNode.dataset.saved === 'true') {
                // If the question is saved in the database, send a delete request to the server
                var xhr = new XMLHttpRequest();
                xhr.open('DELETE', '/delete_question', true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.send(JSON.stringify({
                    question_id: target.parentNode.id.split('_')[1] // Extract the question id from the id attribute
                }));

                xhr.onload = function() {
                    if (xhr.status == 200) {
                        // If the server responded with a status of 200, remove the question from the DOM
                        target.parentNode.remove();
                    } else {
                        // If the server responded with an error status, log the error message
                        console.error('Failed to delete question:', xhr.responseText);
                    }
                };
            } else {
                // If the question is not saved in the database, just remove it from the DOM
                target.parentNode.remove();
            }
        }
    });
});

// Widget icon functionality
window.onload = function() {
    var labels = document.querySelectorAll('#widget_icon label');
    labels.forEach(function(label) {
        var radio = label.querySelector('input');
        if (radio.checked) {
            label.classList.add('selected');
        }
        radio.addEventListener('change', function() {
            labels.forEach(function(label) {
                label.classList.remove('selected');
            });
            if (this.checked) {
                this.parentElement.classList.add('selected');
            }
        });
    });
};

function showPage(pageId) {
    // Hide all subpages
    var subpages = document.getElementsByClassName('subpage');
    for (var i = 0; i < subpages.length; i++) {
        subpages[i].style.display = 'none';
    }

    // Show the selected subpage
    document.getElementById(pageId).style.display = 'block';

    // Remove the 'selected' class from all buttons
    var buttons = document.getElementsByClassName('button-35');
    for (var i = 0; i < buttons.length; i++) {
        buttons[i].classList.remove('selected');
    }

    // Add the 'selected' class to the clicked button
    if (pageId === 'styling-settings') {
        document.querySelector('button[onclick="showPage(\'styling-settings\')"]').classList.add('selected');
    } else if (pageId === 'system-settings') {
        document.querySelector('button[onclick="showPage(\'system-settings\')"]').classList.add('selected');
    } else if (pageId === 'faq-settings') {
        document.querySelector('button[onclick="showPage(\'faq-settings\')"]').classList.add('selected');
    }
}

// jQuery functionality
$(document).ready(function() {
    $('#font_style').select2();

    function formatIcon (icon) {
        var originalOption = icon.element;
        var img = $(originalOption).data('icon');
        if (!icon.id) { return icon.text; }
        var $icon = $(
            '<span><img src="' + img + '" class="img-flag" style="width: 30px; height: 30px;" /> ' + icon.text + '</span>'
        );
        return $icon;
    }

    $('#icon-select').select2({
        templateResult: formatIcon,
        placeholder: "Click to change"
    });

    // Add an event listener for the change event
    $('#icon-select').on('change', function() {
        // Get the selected option
        var selectedOption = $(this).find('option:selected');

        // Get the data-icon attribute of the selected option
        var icon = selectedOption.data('icon');

        // Log the icon variable
        console.log('icon:', icon);

        // Update the src attribute of the img element
        $('#selected-icon').attr('src', icon);
    });
});