/* ----------- static/js/script.js ----------- */
document.addEventListener("DOMContentLoaded", function () {
    // --- Typing effect ---
    const descriptionElement = document.querySelector(".description");
    if (descriptionElement) {
        descriptionElement.textContent = ''; // Clear it
        const text = "Your virtual medical assistant for health information and guidance.";

        function typeText(element, text, speed) {
            let index = 0;
            function type() {
                if (element && index < text.length) {
                    element.textContent += text.charAt(index);
                    index++;
                    setTimeout(type, speed);
                }
            }
            type();
        }
        typeText(descriptionElement, text, 40);
    }

    // Add debug mode (can be toggled in console)
    window.debugMode = false;
    console.log("To enable debug mode, type: window.debugMode = true");
    
    // Create a debug div that can be shown/hidden
    const debugDiv = document.createElement('div');
    debugDiv.id = 'debug-panel';
    debugDiv.style.display = 'none';
    debugDiv.style.position = 'fixed';
    debugDiv.style.bottom = '10px';
    debugDiv.style.right = '10px';
    debugDiv.style.background = 'rgba(0,0,0,0.8)';
    debugDiv.style.color = 'lime';
    debugDiv.style.padding = '10px';
    debugDiv.style.fontSize = '12px';
    debugDiv.style.maxWidth = '300px';
    debugDiv.style.maxHeight = '200px';
    debugDiv.style.overflow = 'auto';
    debugDiv.style.zIndex = '9999';
    debugDiv.style.borderRadius = '5px';
    debugDiv.innerHTML = '<h4>Debug Panel</h4><div id="debug-content"></div>';
    document.body.appendChild(debugDiv);
    
    window.logDebug = function(message) {
        console.log("DEBUG:", message);
        if (window.debugMode) {
            const debugContent = document.getElementById('debug-content');
            if (debugContent) {
                const entry = document.createElement('div');
                entry.textContent = new Date().toLocaleTimeString() + ': ' + message;
                debugContent.appendChild(entry);
                debugDiv.style.display = 'block';
                
                // Scroll to bottom
                debugContent.scrollTop = debugContent.scrollHeight;
            }
        }
    };

    // --- Variables and Elements ---
    const queryInput = document.getElementById('query-input');
    const chatBox = document.getElementById('chat-box');
    const imageBox = document.getElementById('image-box');
    const googleLink = document.getElementById('google-link');
    const youtubeLink = document.getElementById('youtube-link');
    const modeToggleButton = document.getElementById('mode-toggle');
    const body = document.body;
    const modal = document.getElementById('modal');
    const zoomedImage = document.getElementById('zoomed-image');
    const modeIcon = modeToggleButton ? modeToggleButton.querySelector('i') : null;
    const structuredResponse = document.getElementById('structured-response');
    const structuredResponseArea = document.getElementById('structured-response-area');
    const interactiveComponents = document.getElementById('interactive-components');
    const sendButton = document.getElementById('send-button');
    const micButton = document.getElementById('mic-button');
    const suggestionChips = document.querySelectorAll('.suggestion-chip');

    // Track conversation context
    let conversationContext = {
        conversationHistory: [],
        activeFollowUp: false,
        activeRating: false,
        symptomsToRate: [],
        currentRatings: {}
    };

    // --- Event Listeners ---

    // Dark mode toggle
    if (modeToggleButton) {
        modeToggleButton.addEventListener('click', () => {
            body.classList.toggle('dark-mode');
            if (body.classList.contains('dark-mode')) {
                if (modeIcon) modeIcon.className = 'fas fa-sun';
                localStorage.setItem('theme', 'dark-mode');
            } else {
                if (modeIcon) modeIcon.className = 'fas fa-moon';
                localStorage.setItem('theme', 'light-mode');
            }
        });
    }

    // Check for saved theme preference
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark-mode') {
        body.classList.add('dark-mode');
        if (modeIcon) modeIcon.className = 'fas fa-sun';
    } else {
        if (modeIcon) modeIcon.className = 'fas fa-moon';
    }

    // Handle Enter key press
    if (queryInput) {
        queryInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                handleQuery();
            }
        });
    }

    // Send button click handler
    if (sendButton) {
        sendButton.addEventListener('click', () => {
            handleQuery();
        });
    }

    // Microphone button click handler
    if (micButton && 'webkitSpeechRecognition' in window) {
        const recognition = new webkitSpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';

        let isRecording = false;

        micButton.addEventListener('click', () => {
            if (!isRecording) {
                recognition.start();
                micButton.classList.add('recording');
                isRecording = true;
            } else {
                recognition.stop();
                micButton.classList.remove('recording');
                isRecording = false;
            }
        });

        recognition.onresult = function(event) {
            const transcript = event.results[0][0].transcript;
            queryInput.value = transcript;
            micButton.classList.remove('recording');
            isRecording = false;
            
            setTimeout(() => {
                handleQuery();
            }, 500);
        };

        recognition.onerror = function(event) {
            console.error('Speech recognition error:', event.error);
            micButton.classList.remove('recording');
            isRecording = false;
            appendMessage('bot', `I couldn't hear you clearly. Please try typing your question.`);
        };

        recognition.onend = function() {
            micButton.classList.remove('recording');
            isRecording = false;
        };
    } else if (micButton) {
        micButton.style.display = 'none';
        console.log('Speech recognition not supported in this browser');
    }

    // Suggestion chips click handler
    suggestionChips.forEach(chip => {
        chip.addEventListener('click', () => {
            const query = chip.getAttribute('data-query');
            if (query) {
                queryInput.value = query;
                handleQuery();
            }
        });
    });

    // --- Helper Function for Markdown to HTML ---
    function markdownToHtml(markdownText) {
        if (!markdownText) return '';

        let html = markdownText;

        // Handle bold (**text**)
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // Handle italic (*text* - careful not to catch list markers)
        // Use negative lookbehind/lookahead to avoid list markers
        // Simpler approach: Temporarily replace list markers
        html = html.replace(/^\*\s/gm, '__LIST_ITEM_STAR__ ');
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
        html = html.replace(/__LIST_ITEM_STAR__\s/g, '* ');

        // Handle unordered lists (* item or - item)
        html = html.replace(/^\*\s(.*)/gm, '<ul><li>$1</li></ul>');
        html = html.replace(/^-\s(.*)/gm, '<ul><li>$1</li></ul>');
        // Collapse consecutive lists
        html = html.replace(/<\/ul>\n?<ul>/g, '');

        // Handle numbered lists (1. item)
        html = html.replace(/^(\d+)\.\s(.*)/gm, '<ol start="$1"><li>$2</li></ol>');
        // Collapse consecutive numbered lists
        html = html.replace(/<\/ol>\n?<ol start="\d+">/g, '');
        // Fix starting number for collapsed lists - this is tricky without more complex parsing
        // A simpler approach is to just use standard <ol>
        html = html.replace(/^(\d+)\.\s(.*)/gm, '<ol><li>$2</li></ol>');
        html = html.replace(/<\/ol>\n?<ol>/g, '');

        // Handle line breaks (convert remaining newlines to <br>)
        html = html.replace(/\n/g, '<br>');

        return html;
    }

    // --- Core Functions ---

    function handleQuery() {
        if (!queryInput) return;
        const userQuery = queryInput.value.trim();
        if (!userQuery) return;

        // Reset UI elements
        if (structuredResponse) {
            structuredResponse.style.display = 'none';
            structuredResponse.innerHTML = '';
        }
        if (structuredResponseArea) {
            structuredResponseArea.innerHTML = '';
        }
        if (imageBox) {
            imageBox.style.display = 'none';
            imageBox.innerHTML = '';
        }
        if (interactiveComponents) {
            interactiveComponents.innerHTML = '';
        }

        // Update Google search link
        if (googleLink) {
            googleLink.href = `https://www.google.com/search?q=${encodeURIComponent(userQuery)}`;
        }
        
        // Update YouTube search link
        if (youtubeLink) {
            youtubeLink.href = `https://www.youtube.com/results?search_query=${encodeURIComponent(userQuery)}`;
        }
        
        // Fetch Google search images for the query
        // fetchGoogleImages(userQuery); // REMOVED: Moved call inside fetchInteractiveResponse

        // Submit the user message
        submitUserMessage(userQuery);
        
        // Clear input
        queryInput.value = '';
    }

    // Function to fetch Google search images
    function fetchGoogleImages(query) {
        if (!imageBox) return;
        
        const searchTerm = encodeURIComponent(query);
        const url = `/gemini/image/${searchTerm}`;
        
        window.logDebug(`Fetching images for: ${query}`);
        
        fetch(url)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Image search failed: ${response.status}`);
                }
                return response.json();
            })
            .then(imageUrls => {
                displayImages(imageUrls, query);
            })
            .catch(error => {
                console.error('Error fetching images:', error);
                window.logDebug(`Image fetch error: ${error.message}`);
            });
    }
    
    // Function to display images in the imageBox
    function displayImages(imageUrls, query) {
        if (!imageBox || !imageUrls || imageUrls.length === 0) return;
        
        window.logDebug(`Displaying ${imageUrls.length} images`);
        
        // Clear previous images
        imageBox.innerHTML = '';
        
        // Add title for the image section
        const titleEl = document.createElement('h3');
        titleEl.className = 'image-section-title';
        titleEl.innerHTML = `Images for "${query}"`;
        imageBox.appendChild(titleEl);
        
        // Create image gallery
        const galleryEl = document.createElement('div');
        galleryEl.className = 'image-gallery';
        
        // Add images to gallery
        imageUrls.forEach(url => {
            const imgWrapper = document.createElement('div');
            imgWrapper.className = 'image-wrapper';
            
            const img = document.createElement('img');
            img.src = url;
            img.alt = `Search result for: ${query}`;
            img.loading = 'lazy';
            
            // Add click event for zoom
            img.addEventListener('click', () => {
                zoomImage(url);
            });
            
            imgWrapper.appendChild(img);
            galleryEl.appendChild(imgWrapper);
        });
        
        imageBox.appendChild(galleryEl);
        imageBox.style.display = 'block';
    }
    
    // Function to handle image zoom in modal
    function zoomImage(imageUrl) {
        if (!modal || !zoomedImage) return;
        
        zoomedImage.src = imageUrl;
        modal.classList.add('active');
        
        // Close modal when clicked
        modal.addEventListener('click', () => {
            modal.classList.remove('active');
        }, { once: true });
    }
    
    // Initialize modal close on ESC key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal && modal.classList.contains('active')) {
            modal.classList.remove('active');
        }
    });

    async function fetchInteractiveResponse(userMessage) {
        try {
            // Show typing indicator
            showTypingIndicator();
            
            // Set a timeout to handle cases where the server doesn't respond
            let timeoutId = setTimeout(() => {
                hideTypingIndicator();
                removeThinkingMessage();
                appendMessage('bot', "The server is taking too long to respond. Please try again later or restart the conversation.");
                createRestartOption();
            }, 20000);  // 20 second timeout
            
            // Add the user message to conversation context
            conversationContext.conversationHistory.push({
                role: 'user',
                message: userMessage
            });
            
            // Log conversation history for debugging
            console.log("Current conversation history:", conversationContext.conversationHistory);
            window.logDebug(`Conversation history length: ${conversationContext.conversationHistory.length}`);
            
            // POST to the interactive endpoint
            const response = await fetch('/gemini-interactive', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: userMessage,
                    conversation_history: conversationContext.conversationHistory
                })
            });
            
            clearTimeout(timeoutId);
            
            // Remove thinking message and hide typing indicator
            removeThinkingMessage();
            hideTypingIndicator();
            
            // Parse the response
            const result = await response.json();
            const data = result.data;
            
            // Check for error conditions in the response
            if (!data || (data.error && !data.response)) {
                throw new Error(data?.error || "Invalid response from server");
            }
            
            // Handle conversation restart if needed
            if (data.conversation_restarted) {
                // Clear the chat box, keeping only the initial bot message
                const initialBotMessage = chatBox.querySelector('.chat-bubble.bot-message:first-child');
                chatBox.innerHTML = '';
                if (initialBotMessage) {
                    chatBox.appendChild(initialBotMessage);
                }
                
                // Reset conversation context
                conversationContext = {
                    conversationHistory: [],
                    activeFollowUp: false,
                    activeRating: false,
                    symptomsToRate: [],
                    currentRatings: {}
                };
                
                // Add restart message
                appendMessage('bot', data.response);
                enableUserInput();
                return;
            }
            
            // Append the bot's response
            appendMessage('bot', data.response, false, true);
            
            // Add the response to conversation context
            conversationContext.conversationHistory.push({
                role: 'assistant',
                message: data.response
            });
            
            // Clear any existing interactive components
            if (interactiveComponents) {
                interactiveComponents.innerHTML = '';
            }
            
            // Update the progress indicator if we have step information
            if (data.current_step && data.total_steps) {
                updateProgressIndicator(data.current_step, data.total_steps);
            }
            
            // Log debug info
            window.logDebug(`Conversation complete: ${data.conversation_complete}`);
            window.logDebug(`Needs follow-up: ${data.needs_follow_up}`);
            window.logDebug(`Can provide structured response: ${data.can_provide_structured_response}`);
            window.logDebug(`Is medical related: ${data.is_medical_related}`);

            // --- ADDED: Fetch images based on AI-suggested search term --- 
            if (data.image_search_term && data.image_search_term.trim() !== "") {
                window.logDebug(`AI suggested image search term: '${data.image_search_term}', fetching images...`);
                fetchGoogleImages(data.image_search_term.trim());
            } else {
                window.logDebug("No image search term provided by AI, skipping image fetch.");
                // Ensure image box is cleared if no term provided
                if (imageBox) {
                    imageBox.innerHTML = '';
                    imageBox.style.display = 'none';
                }
            }
            // -------------------------------------------------------------
            
            // Handle structured response for medical queries - do this BEFORE follow-up handling
            if (data.is_medical_related !== false && data.can_provide_structured_response) {
                window.logDebug("Displaying structured response for medical query");
                displayStructuredResponse(data);
            } else if (data.conversation_complete && data.is_medical_related !== false) {
                // Force structured display for completed medical conversations
                window.logDebug("Forcing structured response for completed medical conversation");
                data.can_provide_structured_response = true;
                displayStructuredResponse(data);
            }
            
            // Handle follow-up questions - only if conversation isn't marked complete
            if (data.needs_follow_up && !data.conversation_complete) {
                window.logDebug(`Creating follow-up component: ${data.follow_up_type}`);
                
                // Handle different types of follow-up components
                if (data.follow_up_type === 'scale') {
                    createScaleFollowUpComponent(data.follow_up_question || 'How would you rate this?');
                } else if (data.follow_up_type === 'select' && data.follow_up_options && data.follow_up_options.length > 0) {
                    createSelectFollowUpComponent(data.follow_up_question, data.follow_up_options);
                } else if (data.follow_up_type === 'multiselect' && data.follow_up_options && data.follow_up_options.length > 0) {
                    createMultiSelectFollowUpComponent(data.follow_up_question, data.follow_up_options);
                } else if (data.follow_up_type === 'checkbox' && data.follow_up_options && data.follow_up_options.length > 0) {
                    createCheckboxFollowUpComponent(data.follow_up_question, data.follow_up_options);
                } else if (data.follow_up_question) {
                    // Default to text input if we have a question but no specific type or invalid type
                    createTextFollowUpComponent(data.follow_up_question);
                } else {
                    // If no question provided but needs_follow_up is true, create a generic text input
                    createTextFollowUpComponent("Please provide more information:");
                }
                
                // Mark as having an active follow-up
                conversationContext.activeFollowUp = true;
                
                // We keep input disabled as the user should interact with the follow-up component
                // The submit button in the component will enable input again
            } 
            // Handle symptom ratings if requested - only if conversation isn't marked complete
            else if (data.rate_symptoms && data.symptoms_to_rate && data.symptoms_to_rate.length > 0 && !data.conversation_complete) {
                window.logDebug(`Creating symptom rating for: ${data.symptoms_to_rate.join(', ')}`);
                createSymptomRatingComponent(data.symptoms_to_rate);
                conversationContext.activeRating = true;
                conversationContext.symptomsToRate = data.symptoms_to_rate;
                
                // We keep input disabled as the user should interact with the rating component
            }
            // Handle conversation completion - provide restart option
            else if (data.conversation_complete) {
                window.logDebug(`Conversation complete - Medical: ${data.is_medical_related !== false}`);
                createRestartOption();
                enableUserInput(); // Allow new queries even with completed conversation
            }
            // If no special handling was needed, make sure user input is enabled
            else {
                window.logDebug("No special components needed - enabling user input");
                enableUserInput();
            }
            
        } catch (error) {
            console.error('Error fetching response:', error);
            window.logDebug(`Error: ${error.message}`);
            
            // Remove thinking message and hide typing indicator
            removeThinkingMessage();
            hideTypingIndicator();
            
            // Show error message to user
            appendMessage('bot', "I'm having trouble connecting. Please try again or reload the page.");
            
            // Always make sure user can continue typing after an error
            enableUserInput();
            
            // Create restart option after error
            createRestartOption();
        }
    }

    function displayStructuredResponse(data) {
        // Get the container
        const container = document.getElementById('structured-response-area');
        if (!container) return;
        
        container.innerHTML = '';
        
        // Check if this is a non-medical query
        if (data.is_medical_related === false || data.is_medical_related_prompt === "No") {
            console.log("Non-medical query - hiding structured response");
            container.style.display = 'none';
            return;
        }
        
        // For medical queries, create structured response container
        window.logDebug("Creating structured response for medical query");
        
        // Ensure we have required fields with default values if needed
        if (!data.Symptoms || data.Symptoms === '') data.Symptoms = '.';
        if (!data.Remedies) data.Remedies = '';
        if (!data.Precautions) data.Precautions = '';
        if (!data.Guidelines) data.Guidelines = '';
        if (!data.medication) data.medication = [];
        if (!data.Disclaimer) data.Disclaimer = "I am a chatbot, not a doctor, and cannot provide a diagnosis. This information is not a substitute for professional medical advice. If you're experiencing symptoms, please consult with a healthcare professional.";
        
        console.log("Structured data:", {
            Symptoms: data.Symptoms,
            Remedies: data.Remedies,
            Precautions: data.Precautions,
            Guidelines: data.Guidelines,
            medication: data.medication,
            Disclaimer: data.Disclaimer
        });
        
        const wrapper = document.createElement('div');
        wrapper.className = 'structured-response-wrapper';
        
        // Add heading
        const heading = document.createElement('h3');
        heading.textContent = 'Assessment Information';
        heading.className = 'structured-heading';
        wrapper.appendChild(heading);
        
        // Create sections for required fields
        const sections = [
            { key: 'Symptoms', icon: 'fas fa-clipboard-list', defaultText: 'No specific symptoms reported.', className: 'symptoms-section' },
            { key: 'Remedies', icon: 'fas fa-prescription-bottle-alt', defaultText: 'No specific remedies recommended at this time.', className: 'remedies-section' },
            { key: 'Precautions', icon: 'fas fa-shield-alt', defaultText: 'No specific precautions noted.', className: 'precautions-section' },
            { key: 'Guidelines', icon: 'fas fa-book-medical', defaultText: 'Always consult a healthcare professional for medical concerns.', className: 'guidelines-section' },
            { key: 'medication', icon: 'fas fa-pills', defaultText: 'No specific OTC medication types suggested.', className: 'medication-section' }
        ];
        
        // Always show all sections for medical queries
        sections.forEach(section => {
            const content = data[section.key];
            
            // Skip medication section if content is empty array or null
            if (section.key === 'medication' && (!content || !Array.isArray(content) || content.length === 0)) {
                return; // Don't render empty medication section
            }
            
            const sectionEl = document.createElement('div');
            sectionEl.className = `structured-section ${section.className}`;
            
            const header = document.createElement('div');
            header.className = 'section-header';
            
            const iconEl = document.createElement('i');
            iconEl.className = section.icon;
            header.appendChild(iconEl);
            
            const titleEl = document.createElement('h4');
            titleEl.textContent = section.key;
            header.appendChild(titleEl);
            
            sectionEl.appendChild(header);
            
            const contentEl = document.createElement('div');
            contentEl.className = 'section-content';
            
            // Handle special case for empty symptoms or empty content
            let displayContent = content;
            if (section.key !== 'medication' && (!content || content === '' || content === '.')) {
                displayContent = section.defaultText;
            } else if (section.key === 'medication') {
                // Format medication list as chips
                if (Array.isArray(content) && content.length > 0) {
                    const chipsContainer = document.createElement('div');
                    chipsContainer.className = 'medication-chips-container';
                    content.forEach(med => {
                        const chip = document.createElement('span');
                        chip.className = 'medication-chip';

                        // Create and add the icon
                        const icon = document.createElement('i');
                        icon.className = 'fas fa-tablets'; // Or fas fa-capsules, fas fa-pills etc.
                        icon.style.marginLeft = '0.5em'; // Add space before the icon
                        icon.style.marginRight = '0.5em'; // Adjust space between icon and text (approx 2 spaces)
                        chip.appendChild(icon);

                        // Add the medication text after the icon
                        chip.appendChild(document.createTextNode(med));

                        chipsContainer.appendChild(chip);
                    });
                    displayContent = chipsContainer.outerHTML; // Use the generated HTML string
                } else {
                    displayContent = section.defaultText; // Show default if array is empty after checks
                }
            }
            
            // Format the content with proper HTML for lists and line breaks
            if (section.key !== 'medication') {
                displayContent = formatStructuredContent(displayContent);
            }
            contentEl.innerHTML = displayContent;
            sectionEl.appendChild(contentEl);
            
            wrapper.appendChild(sectionEl);
        });
        
        // Add disclaimer
        const disclaimer = document.createElement('div');
        disclaimer.className = 'medical-disclaimer';
        
        const disclaimerIcon = document.createElement('i');
        disclaimerIcon.className = 'fas fa-exclamation-triangle';
        disclaimer.appendChild(disclaimerIcon);
        
        const disclaimerText = document.createElement('p');
        disclaimerText.textContent = data.Disclaimer;
        disclaimer.appendChild(disclaimerText);
        
        wrapper.appendChild(disclaimer);
        
        // Add to container
        container.appendChild(wrapper);
        container.style.display = 'block';
        
        // Scroll to the structured response
        container.scrollIntoView({ behavior: 'smooth' });
    }

    function formatStructuredContent(content) {
        if (!content) return '';
        
        let formatted = content;

        // --- NEW: Handle "**Topic:** Description" format first ---
        // Convert **Topic:** Description (potentially across multiple lines) into paragraphs
        // Split by newline, process lines starting with **
        let lines = formatted.split(/\r?\n/); // Split by newline
        let resultHTML = '';
        let currentParagraph = '';

        lines.forEach(line => {
            line = line.trim();
            if (line.startsWith('**')) {
                // If we were building a paragraph, finish it first
                if (currentParagraph) {
                    resultHTML += `<p>${currentParagraph.trim()}</p>`;
                }
                // Start a new paragraph with the bolded part
                currentParagraph = line.replace(/\*\*(.*?)\*\*/, '<strong>$1</strong>');
            } else if (currentParagraph && line) {
                // Continue the current paragraph
                currentParagraph += ' ' + line;
            } else if (line) {
                // If it's a line that doesn't start with ** and we're not in a paragraph,
                // treat it as its own paragraph (handles simple text cases)
                 if (currentParagraph) {
                     resultHTML += `<p>${currentParagraph.trim()}</p>`;
                     currentParagraph = '';
                 }
                 resultHTML += `<p>${line}</p>`;
            }
        });
        // Add any remaining paragraph content
        if (currentParagraph) {
            resultHTML += `<p>${currentParagraph.trim()}</p>`;
        }
        
        // If resultHTML is empty, it means the specific format wasn't found, try old list formatting
        if (!resultHTML.trim()) {
            formatted = content.replace(/•/g, '');
            // Convert remaining line breaks to HTML
            formatted = formatted.replace(/\n/g, '<br>');
            
             // --- OLD List handling (as fallback) ---
             if (formatted.match(/\d+\.\s/)) {
                 let listLines = formatted.split('<br>');
                 let inList = false;
                 let listItems = [];
                 let fallbackResult = '';
                 listLines.forEach(line => {
                     const numberedMatch = line.trim().match(/^(\d+)\.\s+(.*)/);
                     if (numberedMatch) {
                         listItems.push(numberedMatch[2]);
                         inList = true;
                     } else if (inList) {
                         fallbackResult += '<ol><li>' + listItems.join('</li><li>') + '</li></ol>';
                         listItems = [];
                         inList = false;
                         if (line.trim()) fallbackResult += line + '<br>';
                     } else {
                         if (line.trim()) fallbackResult += line + '<br>';
                     }
                 });
                 if (inList && listItems.length > 0) fallbackResult += '<ol><li>' + listItems.join('</li><li>') + '</li></ol>';
                 formatted = fallbackResult;
             } else if (formatted.includes('-') || formatted.includes('*')) {
                 let listLines = formatted.split('<br>');
                 let inList = false;
                 let listItems = [];
                 let fallbackResult = '';
                 listLines.forEach(line => {
                     if (line.trim().match(/^[-*]\s/)) {
                         listItems.push(line.trim().replace(/^[-*]\s/, ''));
                         inList = true;
                     } else if (inList) {
                         fallbackResult += '<ul><li>' + listItems.join('</li><li>') + '</li></ul>';
                         listItems = [];
                         inList = false;
                         if (line.trim()) fallbackResult += line + '<br>';
                     } else {
                         if (line.trim()) fallbackResult += line + '<br>';
                     }
                 });
                 if (inList && listItems.length > 0) fallbackResult += '<ul><li>' + listItems.join('</li><li>') + '</li></ul>';
                 formatted = fallbackResult;
             }
             // --- End OLD List Handling ---
            resultHTML = formatted; // Use the fallback list/br formatting
        }
        
        // Replace the old formatting logic with the new resultHTML
        formatted = resultHTML;

        // Enhance visibility of emergency instructions
        if (formatted.includes('IMPORTANT') || 
            formatted.includes('SEEK IMMEDIATE') || 
            formatted.includes('EMERGENCY')) {
            
            // Find and wrap emergency instructions in warning divs
            const lines = formatted.split('<br>');
            let enhancedLines = [];
            
            let inEmergencyBlock = false;
            let emergencyContent = [];
            
            lines.forEach(line => {
                if (line.includes('IMPORTANT') || line.includes('SEEK IMMEDIATE') || line.includes('EMERGENCY')) {
                    // Start a new emergency block if not already in one
                    if (!inEmergencyBlock) {
                        inEmergencyBlock = true;
                        emergencyContent = [line];
                    } else {
                        emergencyContent.push(line);
                    }
                } else if (inEmergencyBlock) {
                    // If this is a blank line or doesn't continue the emergency content, end the block
                    if (!line.trim()) {
                        enhancedLines.push(`<div class="high-severity-warning">${emergencyContent.join('<br>')}</div>`);
                        inEmergencyBlock = false;
                        emergencyContent = [];
                    } else {
                        emergencyContent.push(line);
                    }
                } else {
                    enhancedLines.push(line);
                }
            });
            
            // Add any remaining emergency content
            if (inEmergencyBlock && emergencyContent.length > 0) {
                enhancedLines.push(`<div class="high-severity-warning">${emergencyContent.join('<br>')}</div>`);
            }
            
            formatted = enhancedLines.join('<br>');
        }
        
        // Add emphasis to key medical and emergency phrases
        formatted = formatted.replace(/\b(important|caution|warning|avoid|immediately|seek medical|emergency|emergency care|urgent care|call 911|hospital|severe|high fever|shortness of breath|difficulty breathing|chest pain|doctor|physician)\b/gi, 
            '<strong class="highlight-important">$1</strong>');
        
        return formatted;
    }

    function createSymptomRatingComponent(symptoms) {
        // Clear any existing components
        const container = document.getElementById('interactive-components');
        container.innerHTML = '';
        
        // Add title
        const title = document.createElement('h3');
        title.textContent = 'Please rate your symptoms:';
        title.className = 'rating-title';
        container.appendChild(title);
        
        // Create wrapper for all ratings
        const ratingsWrapper = document.createElement('div');
        ratingsWrapper.className = 'symptom-ratings-wrapper';
        container.appendChild(ratingsWrapper);
        
        // Track ratings
        const ratings = {};
        
        // Create slider for each symptom
        symptoms.forEach(symptom => {
            const ratingContainer = document.createElement('div');
            ratingContainer.className = 'symptom-rating-container';
            
            const label = document.createElement('label');
            label.textContent = symptom + ':';
            label.className = 'symptom-label';
            ratingContainer.appendChild(label);
            
            const sliderContainer = document.createElement('div');
            sliderContainer.className = 'slider-container';
            
            const valueDisplay = document.createElement('span');
            valueDisplay.className = 'rating-value';
            valueDisplay.textContent = '5';
            
            const slider = document.createElement('input');
            slider.type = 'range';
            slider.min = '1';
            slider.max = '10';
            slider.value = '5';
            slider.className = 'symptom-slider';
            
            // Initialize default rating
            ratings[symptom] = 5;
            
            // Update value display on change
            slider.addEventListener('input', function() {
                valueDisplay.textContent = this.value;
                ratings[symptom] = parseInt(this.value);
            });
            
            sliderContainer.appendChild(slider);
            sliderContainer.appendChild(valueDisplay);
            
            ratingContainer.appendChild(sliderContainer);
            ratingsWrapper.appendChild(ratingContainer);
        });
        
        // Add submit button
        const submitButton = document.createElement('button');
        submitButton.textContent = 'Submit Ratings';
        submitButton.className = 'submit-btn';
        submitButton.addEventListener('click', function() {
            // Format the ratings into a message
            let ratingMessage = "Symptom ratings:\n";
            for (const symptom in ratings) {
                ratingMessage += `${symptom}: ${ratings[symptom]}/10\n`;
            }
            
            // Send the ratings
            submitUserMessage(ratingMessage);
            
            // Clear the rating component
            container.innerHTML = '';
        });
        
        container.appendChild(submitButton);
        
        // Make sure the component is visible
        container.style.display = 'block';
    }

    function createRestartOption() {
        // Check if restart option already exists to prevent duplicates
        if (document.querySelector('.restart-option')) {
            return;
        }
        
        const restartContainer = document.createElement('div');
        restartContainer.className = 'restart-option';
        restartContainer.innerHTML = `
            <p>Would you like to start a new conversation?</p>
            <button class="restart-button"><i class="fas fa-redo-alt"></i> Start New Conversation</button>
        `;
        
        // Add restart button click handler
        const restartButton = restartContainer.querySelector('.restart-button');
        restartButton.addEventListener('click', () => {
            // Send a restart message to the server
            // Do NOT include this in the conversation history 
            fetch('/gemini-interactive', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: "restart",
                    conversation_history: null // Explicitly send null to signal restart
                })
            });
            
            // Visually clear the chat immediately for better UX
            const initialBotMessage = chatBox.querySelector('.chat-bubble.bot-message:first-child');
            chatBox.innerHTML = '';
            if (initialBotMessage) {
                chatBox.appendChild(initialBotMessage);
            } else {
                // Add a welcome message if no initial message exists
                appendMessage('bot', 'Hello! I\'m MedAssist, an AI medical assistant. How can I help you with your health questions today?');
            }
            
            // Reset conversation context completely
            conversationContext = {
                conversationHistory: [],
                activeFollowUp: false,
                activeRating: false,
                symptomsToRate: [],
                currentRatings: {}
            };
            
            // Re-enable input
            enableUserInput();
            
            // Clear any structured response
            if (structuredResponse) {
                structuredResponse.style.display = 'none';
                structuredResponse.innerHTML = '';
            }
            
            if (structuredResponseArea) {
                structuredResponseArea.style.display = 'none';
                structuredResponseArea.innerHTML = '';
            }
            
            // Clear any interactive components
            if (interactiveComponents) {
                interactiveComponents.innerHTML = '';
            }
        });
        
        interactiveComponents.appendChild(restartContainer);
    }

    // Function to update the progress indicator
    function updateProgressIndicator(currentStep, totalSteps) {
        const container = document.getElementById('interactive-components');
        
        // Check if progress indicator already exists
        let progressContainer = document.querySelector('.progress-indicator-container');
        
        if (!progressContainer) {
            // Create progress container
            progressContainer = document.createElement('div');
            progressContainer.className = 'progress-indicator-container';
            
            // Create text label
            const progressLabel = document.createElement('span');
            progressLabel.className = 'progress-label';
            progressContainer.appendChild(progressLabel);
            
            // Create progress bar
            const progressBar = document.createElement('div');
            progressBar.className = 'progress-bar-outer';
            
            const progressInner = document.createElement('div');
            progressInner.className = 'progress-bar-inner';
            progressBar.appendChild(progressInner);
            
            progressContainer.appendChild(progressBar);
            
            // Add to container before other elements
            container.insertBefore(progressContainer, container.firstChild);
        }
        
        // Update progress text and bar
        const progressLabel = progressContainer.querySelector('.progress-label');
        progressLabel.textContent = ``;
        
        const progressInner = progressContainer.querySelector('.progress-bar-inner');
        const progressPercentage = (currentStep / totalSteps) * 100;
        progressInner.style.width = `${progressPercentage}%`;
    }

    function appendMessage(sender, message, isThinking = false, showAvatar = false) {
        if (!chatBox) return;
        
        // For thinking messages, either update the existing one or add a new one
        if (isThinking) {
            const existingThinking = chatBox.querySelector('.thinking');
            if (existingThinking) {
                existingThinking.querySelector('.message-content p').textContent = message;
                return;
            }
        }
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-bubble ${sender}-message`;
        
        if (isThinking) {
            messageDiv.classList.add('thinking');
        }
        
        if (showAvatar) {
            messageDiv.classList.add('with-avatar');
        }
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        
        // Add header for bot messages
        if (sender === 'bot' && !isThinking) {
            const header = document.createElement('p');
            header.className = 'message-header';
            header.textContent = '';
            messageContent.appendChild(header);
        }
        
        // Add message text - wrap it in a paragraph for better consistency
        const text = document.createElement('p');
        text.className = 'message-text';
        // text.textContent = message; // OLD
        // NEW: Render markdown for bot messages
        if (sender === 'bot' && !isThinking) {
            text.innerHTML = markdownToHtml(message);
        } else {
            text.textContent = message; // Keep simple text for user messages and thinking indicators
        }
        messageContent.appendChild(text);
        
        // Add footer for bot messages
        if (sender === 'bot' && !isThinking) {
            const footer = document.createElement('p');
            footer.className = 'message-footer';
            footer.textContent = '';
            messageContent.appendChild(footer);
        }
        
        messageDiv.appendChild(messageContent);
        chatBox.appendChild(messageDiv);
        
        // Scroll to bottom
        chatBox.scrollTop = chatBox.scrollHeight;
        
        // Make sure interactive components are displayed after the newest bot message
        if (sender === 'bot' && !isThinking) {
            const interactiveContainer = document.getElementById('interactive-components');
            if (interactiveContainer) {
                // Move interactive-components after the chat container
                const chatContainer = document.getElementById('chat-box');
                if (chatContainer && chatContainer.parentNode) {
                    chatContainer.parentNode.insertBefore(interactiveContainer, chatContainer.nextSibling);
                }
            }
        }
    }

    function removeThinkingMessage() {
        const thinkingMessage = chatBox.querySelector('.thinking');
        if (thinkingMessage) {
            thinkingMessage.remove();
        }
    }

    function submitUserMessage(message) {
        // Display user message
        appendMessage('user', message);
        
        // Reset the activeFollowUp flag to allow new follow-up components to appear
        conversationContext.activeFollowUp = false;
        
        // Disable user input while processing
        disableUserInput();
        
        // Process the message using the updated fetchInteractiveResponse
        fetchInteractiveResponse(message);
    }

    function enableUserInput() {
        if (queryInput) queryInput.disabled = false;
        if (sendButton) sendButton.disabled = false;
        if (micButton) micButton.disabled = false;
        if (queryInput) queryInput.focus();
    }

    function disableUserInput() {
        if (queryInput) queryInput.disabled = true;
        if (sendButton) sendButton.disabled = true;
        if (micButton) micButton.disabled = true;
    }

    function showTypingIndicator() {
        appendMessage('bot', 'Thinking', true);
    }

    function hideTypingIndicator() {
        removeThinkingMessage();
    }

    function createTextFollowUpComponent(question) {
        const container = document.getElementById('interactive-components');
        if (!container) return;
        
        // Clear any existing content
        container.innerHTML = '';
        
        // Create follow-up container
        const followUpContainer = document.createElement('div');
        followUpContainer.className = 'follow-up-container';
        
        // Create question label
        const questionLabel = document.createElement('div');
        questionLabel.className = 'follow-up-question';
        questionLabel.textContent = question;
        followUpContainer.appendChild(questionLabel);
        
        // Create input and button container
        const inputContainer = document.createElement('div');
        inputContainer.className = 'follow-up-input-container';
        
        // Create text input
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'follow-up-input';
        input.placeholder = 'Type your answer here...';
        
        // Handle enter key
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                submitFollowUp();
            }
        });
        
        inputContainer.appendChild(input);
        
        // Create submit button
        const submitButton = document.createElement('button');
        submitButton.className = 'follow-up-submit';
        submitButton.textContent = 'Submit';
        submitButton.addEventListener('click', submitFollowUp);
        
        inputContainer.appendChild(submitButton);
        followUpContainer.appendChild(inputContainer);
        
        // Add to main container
        container.appendChild(followUpContainer);
        container.style.display = 'block';
        
        // Focus the input
        input.focus();
        
        // Submit function
        function submitFollowUp() {
            const answer = input.value.trim();
            if (answer) {
                // Reset active follow-up flag
                conversationContext.activeFollowUp = false;
                
                // Submit the user message
                submitUserMessage(answer);
            }
        }
    }

    function createScaleFollowUpComponent(question) {
        const container = document.getElementById('interactive-components');
        if (!container) return;
        
        // Clear any existing content
        container.innerHTML = '';
        
        // Create scale container
        const scaleContainer = document.createElement('div');
        scaleContainer.className = 'scale-container';
        
        // Create question label
        const questionLabel = document.createElement('div');
        questionLabel.className = 'follow-up-question';
        questionLabel.textContent = question;
        scaleContainer.appendChild(questionLabel);
        
        // Create scale UI
        const scaleUI = document.createElement('div');
        scaleUI.className = 'scale-ui';
        
        // Create scale value display
        const valueDisplay = document.createElement('div');
        valueDisplay.className = 'scale-value';
        valueDisplay.textContent = '5';
        
        // Create slider
        const slider = document.createElement('input');
        slider.type = 'range';
        slider.min = '1';
        slider.max = '10';
        slider.value = '5';
        slider.className = 'scale-slider';
        
        // Update value display when slider changes
        slider.addEventListener('input', function() {
            valueDisplay.textContent = this.value;
            // Change color based on value
            const value = parseInt(this.value, 10);
            if (value <= 3) {
                valueDisplay.style.backgroundColor = '#3498db'; // blue for low values
            } else if (value <= 7) {
                valueDisplay.style.backgroundColor = '#9b59b6'; // purple for medium values
            } else {
                valueDisplay.style.backgroundColor = '#e74c3c'; // red for high values
            }
        });
        
        // Add scale components
        scaleUI.appendChild(slider);
        scaleUI.appendChild(valueDisplay);
        
        scaleContainer.appendChild(scaleUI);
        
        // Add scale labels
        const scaleLabels = document.createElement('div');
        scaleLabels.className = 'scale-labels';
        
        const minLabel = document.createElement('span');
        minLabel.className = 'scale-min-label';
        minLabel.textContent = 'Mild (1)';
        
        const maxLabel = document.createElement('span');
        maxLabel.className = 'scale-max-label';
        maxLabel.textContent = 'Severe (10)';
        
        scaleLabels.appendChild(minLabel);
        scaleLabels.appendChild(maxLabel);
        scaleContainer.appendChild(scaleLabels);
        
        // Create submit button
        const submitButton = document.createElement('button');
        submitButton.className = 'follow-up-submit';
        
        // Add icon to submit button
        const submitIcon = document.createElement('i');
        submitIcon.className = 'fas fa-check';
        submitButton.appendChild(submitIcon);
        submitButton.appendChild(document.createTextNode(' Submit Rating'));
        
        submitButton.addEventListener('click', function() {
            const value = slider.value;
            // Reset active follow-up flag
            conversationContext.activeFollowUp = false;
            
            submitUserMessage(`My rating is ${value}/10`);
        });
        
        scaleContainer.appendChild(submitButton);
        
        // Add to main container
        container.appendChild(scaleContainer);
        container.style.display = 'block';
    }

    function createSelectFollowUpComponent(question, options) {
        const container = document.getElementById('interactive-components');
        if (!container) return;
        
        // Clear any existing content
        container.innerHTML = '';
        
        // Create select container
        const selectContainer = document.createElement('div');
        selectContainer.className = 'select-container';
        
        // Create question label
        const questionLabel = document.createElement('div');
        questionLabel.className = 'follow-up-question';
        questionLabel.textContent = question;
        selectContainer.appendChild(questionLabel);
        
        // Create options
        const optionsContainer = document.createElement('div');
        optionsContainer.className = 'select-options';
        
        // Create options buttons
        options.forEach(option => {
            const optionButton = document.createElement('button');
            optionButton.className = 'select-option';
            optionButton.textContent = option;
            
            // Add appropriate icon based on option content
            if (option.toLowerCase() === 'yes') {
                optionButton.innerHTML = '<i class="fas fa-check" style="color: #27ae60; margin-right: 8px;"></i> ' + option;
            } else if (option.toLowerCase() === 'no') {
                optionButton.innerHTML = '<i class="fas fa-times" style="color: #e74c3c; margin-right: 8px;"></i> ' + option;
            } else if (option.toLowerCase().includes('not sure') || option.toLowerCase().includes('sometimes')) {
                optionButton.innerHTML = '<i class="fas fa-question" style="color: #f39c12; margin-right: 8px;"></i> ' + option;
            }
            
            optionButton.addEventListener('click', function() {
                // Highlight the selected option
                document.querySelectorAll('.select-option').forEach(btn => {
                    btn.style.borderColor = '#d8e2f3';
                    btn.style.fontWeight = 'normal';
                });
                this.style.borderColor = '#3498db';
                this.style.fontWeight = 'bold';
                
                // Reset active follow-up flag
                conversationContext.activeFollowUp = false;
                
                // Submit after a small delay to show the selection
                setTimeout(() => {
                    submitUserMessage(option);
                }, 300);
            });
            
            optionsContainer.appendChild(optionButton);
        });
        
        selectContainer.appendChild(optionsContainer);
        
        // Add to main container
        container.appendChild(selectContainer);
        container.style.display = 'block';
    }

    function createMultiSelectFollowUpComponent(question, options) {
        const container = document.getElementById('interactive-components');
        if (!container) return;
        
        // Clear any existing content
        container.innerHTML = '';
        
        // Create multi-select container
        const multiSelectContainer = document.createElement('div');
        multiSelectContainer.className = 'multi-select-container';
        
        // Create question label
        const questionLabel = document.createElement('div');
        questionLabel.className = 'follow-up-question';
        questionLabel.textContent = question;
        multiSelectContainer.appendChild(questionLabel);
        
        // Create options
        const optionsContainer = document.createElement('div');
        optionsContainer.className = 'multi-select-options';
        
        // Track selected options
        const selectedOptions = [];
        
        // Create checkbox options
        options.forEach(option => {
            const optionContainer = document.createElement('label');
            optionContainer.className = 'multi-select-option';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = option;
            checkbox.addEventListener('change', function() {
                if (this.checked) {
                    if (!selectedOptions.includes(option)) {
                        selectedOptions.push(option);
                    }
                    // If "None of these" is selected, uncheck all others
                    if (option.toLowerCase().includes('none') || option.toLowerCase() === 'other') {
                        options.forEach(opt => {
                            if (opt !== option) {
                                const otherCheckbox = optionsContainer.querySelector(`input[value="${opt}"]`);
                                if (otherCheckbox && otherCheckbox.checked) {
                                    otherCheckbox.checked = false;
                                    const index = selectedOptions.indexOf(opt);
                                    if (index > -1) {
                                        selectedOptions.splice(index, 1);
                                    }
                                }
                            }
                        });
                    } else {
                        // If any other option is selected, uncheck "None of these"
                        const noneCheckbox = optionsContainer.querySelector('input[value="None of these"]');
                        const otherCheckbox = optionsContainer.querySelector('input[value="Other"]');
                        if (noneCheckbox && noneCheckbox.checked) {
                            noneCheckbox.checked = false;
                            const index = selectedOptions.indexOf('None of these');
                            if (index > -1) {
                                selectedOptions.splice(index, 1);
                            }
                        }
                        if (otherCheckbox && otherCheckbox.checked) {
                            otherCheckbox.checked = false;
                            const index = selectedOptions.indexOf('Other');
                            if (index > -1) {
                                selectedOptions.splice(index, 1);
                            }
                        }
                    }
                } else {
                    const index = selectedOptions.indexOf(option);
                    if (index > -1) {
                        selectedOptions.splice(index, 1);
                    }
                }
            });
            
            // Create the option label
            const optionLabel = document.createElement('span');
            optionLabel.textContent = option;
            
            // Add to container
            optionContainer.appendChild(checkbox);
            optionContainer.appendChild(optionLabel);
            optionsContainer.appendChild(optionContainer);
        });
        
        multiSelectContainer.appendChild(optionsContainer);
        
        // Create submit button
        const submitButton = document.createElement('button');
        submitButton.className = 'follow-up-submit';
        submitButton.innerHTML = '<i class="fas fa-paper-plane"></i> Submit Selections';
        submitButton.addEventListener('click', function() {
            if (selectedOptions.length === 0) {
                alert('Please select at least one option.');
                return;
            }
            
            let message = '';
            if (selectedOptions.length === 1) {
                message = `I selected: ${selectedOptions[0]}`;
            } else {
                const lastOption = selectedOptions.pop();
                message = `I selected: ${selectedOptions.join(', ')} and ${lastOption}`;
                selectedOptions.push(lastOption); // Restore the array
            }
            
            // Reset active follow-up flag
            conversationContext.activeFollowUp = false;
            
            submitUserMessage(message);
        });
        
        multiSelectContainer.appendChild(submitButton);
        
        // Add to main container
        container.appendChild(multiSelectContainer);
        container.style.display = 'block';
    }

    function createCheckboxFollowUpComponent(question, options) {
        const container = document.getElementById('interactive-components');
        if (!container) return;
        
        // Clear any existing content
        container.innerHTML = '';
        
        // Create checkbox container (similar to multi-select but with a different name)
        const checkboxContainer = document.createElement('div');
        checkboxContainer.className = 'checkbox-container';
        
        // Create question label
        const questionLabel = document.createElement('div');
        questionLabel.className = 'follow-up-question';
        questionLabel.textContent = question;
        checkboxContainer.appendChild(questionLabel);
        
        // Create options (reuse the multi-select options structure)
        const optionsContainer = document.createElement('div');
        optionsContainer.className = 'multi-select-options';
        
        // Track selected options
        const selectedOptions = [];
        
        // Create checkbox options - same as multi-select
        options.forEach(option => {
            const optionContainer = document.createElement('label');
            optionContainer.className = 'multi-select-option';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = option;
            checkbox.addEventListener('change', function() {
                if (this.checked) {
                    if (!selectedOptions.includes(option)) {
                        selectedOptions.push(option);
                    }
                } else {
                    const index = selectedOptions.indexOf(option);
                    if (index > -1) {
                        selectedOptions.splice(index, 1);
                    }
                }
            });
            
            const optionLabel = document.createElement('span');
            optionLabel.textContent = option;
            
            optionContainer.appendChild(checkbox);
            optionContainer.appendChild(optionLabel);
            optionsContainer.appendChild(optionContainer);
        });
        
        checkboxContainer.appendChild(optionsContainer);
        
        // Create submit button
        const submitButton = document.createElement('button');
        submitButton.className = 'follow-up-submit';
        submitButton.innerHTML = '<i class="fas fa-check"></i> Confirm Selections';
        submitButton.addEventListener('click', function() {
            if (selectedOptions.length === 0) {
                alert('Please select at least one option.');
                return;
            }
            
            let message = '';
            if (selectedOptions.length === 1) {
                message = `Selected option: ${selectedOptions[0]}`;
            } else {
                const lastOption = selectedOptions.pop();
                message = `Selected options: ${selectedOptions.join(', ')} and ${lastOption}`;
                selectedOptions.push(lastOption); // Restore the array
            }
            
            // Reset active follow-up flag
            conversationContext.activeFollowUp = false;
            
            submitUserMessage(message);
        });
        
        checkboxContainer.appendChild(submitButton);
        
        // Add to main container
        container.appendChild(checkboxContainer);
        container.style.display = 'block';
    }
}); 