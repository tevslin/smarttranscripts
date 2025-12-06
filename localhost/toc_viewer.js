import { initializeDirectory } from './directory.js';

document.addEventListener('DOMContentLoaded', async () => {
    const tocPane = document.getElementById('toc-pane');
    const tocContent = document.getElementById('toc-content');
    const pinButton = document.getElementById('toc-pin-button');
    const resizeHandle = document.getElementById('toc-resize-handle');

    if (!tocPane || !tocContent) return;

    // --- Redirection Logic (Index Page Only) ---
    // Try to open the last visited transcript, or fallback to the first available one.
    // We check for trailing slashes or explicit index.html
    const isIndexPage = window.location.pathname.endsWith('index.html') || window.location.pathname === '/' || window.location.pathname.endsWith('/');

    if (isIndexPage) {
        const urlParams = new URLSearchParams(window.location.search);
        if (!urlParams.has('no_redirect')) {
            const lastOpened = localStorage.getItem('lastOpenedTranscript');
            // Verify lastOpened is really a path and not "null" string
            if (lastOpened && lastOpened !== 'null') {
                window.location.href = lastOpened;
                return; // Stop processing to avoid flash
            }
        }
    } else {
        // We are on a transcript page. Save this as the last opened state.
        // We use the pathname (e.g. /meetings/Committee/Date/transcript.html)
        localStorage.setItem('lastOpenedTranscript', window.location.pathname);
    }

    // --- Initialization ---
    // Wrap header and content in a container for flyout behavior
    let tocWrapper = document.getElementById('toc-wrapper');
    if (!tocWrapper) {
        tocWrapper = document.createElement('div');
        tocWrapper.id = 'toc-wrapper';
        // Move header and content into wrapper
        const header = document.getElementById('toc-header');
        const content = document.getElementById('toc-content');
        if (header) tocWrapper.appendChild(header);
        if (content) tocWrapper.appendChild(content);

        // Insert wrapper into pane (resize handle stays outside)
        tocPane.insertBefore(tocWrapper, resizeHandle);
    }

    // Initialize directory
    // We await this so we can perform post-render actions (like fallback redirect)
    await initializeDirectory(document.getElementById('toc-content'), {
        activePath: window.location.pathname, // Highlights current page
        linkHrefGenerator: (path) => path
    });

    // --- Fallback Redirection (Index Page Only) ---
    // If we are still here (didn't redirect to lastOpened), and we are on index page,
    // open the first item in the list.
    if (isIndexPage) {
        const urlParams = new URLSearchParams(window.location.search);
        if (!urlParams.has('no_redirect')) {
            // We didn't redirect to lastOpened, so try the first item
            const firstLink = document.querySelector('#toc-content a.toc-link');
            if (firstLink) {
                window.location.href = firstLink.href;
                return;
            }
        }
    }

    // --- Pinning Logic ---
    let savedState = null;
    try {
        savedState = localStorage.getItem('tocPinned');
    } catch (e) {
        console.warn('localStorage not accessible:', e);
    }
    let isPinned = savedState === null ? true : savedState === 'true';

    // Force pinned on index page (though we redirect usually, but if no_redirect used)
    if (isIndexPage) {
        isPinned = true;
    }

    function updatePinState() {
        if (isPinned) {
            tocPane.classList.add('pinned');
            tocPane.classList.remove('unpinned');
            tocPane.classList.remove('expanded'); // Ensure it's not in expanded state
            if (pinButton) {
                pinButton.textContent = '📌'; // Pinned icon
                pinButton.title = "Unpin ToC";
            }
        } else {
            tocPane.classList.remove('pinned');
            tocPane.classList.add('unpinned');
            if (pinButton) {
                pinButton.textContent = '📍'; // Unpinned icon
                pinButton.title = "Pin ToC";
            }
        }

        // Only save state if NOT on index page
        if (!isIndexPage) {
            try {
                localStorage.setItem('tocPinned', isPinned);
            } catch (e) {
                // Ignore write errors
            }
        }
    }

    if (pinButton) {
        if (isIndexPage) {
            pinButton.style.display = 'none';
        }

        pinButton.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent bubbling
            isPinned = !isPinned;
            updatePinState();
        });
    }

    // Outlook-like behavior:
    // When unpinned, clicking the hamburger (or the strip) toggles "expanded" mode (overlay).
    tocPane.addEventListener('click', (e) => {
        if (tocPane.classList.contains('unpinned')) {
            // If clicking the pin button, don't toggle expand (handled above)
            if (e.target === pinButton) return;

            // Toggle expanded state
            tocPane.classList.toggle('expanded');
        }
    });

    // Close expanded pane when clicking outside
    document.addEventListener('click', (e) => {
        if (tocPane.classList.contains('unpinned') && tocPane.classList.contains('expanded')) {
            if (!tocPane.contains(e.target)) {
                tocPane.classList.remove('expanded');
            }
        }
    });

    // Initial state
    updatePinState();

    // --- Resizing Logic ---
    let isResizing = false;

    if (resizeHandle) {
        resizeHandle.addEventListener('mousedown', (e) => {
            isResizing = true;
            document.body.style.cursor = 'ew-resize';
            document.body.classList.add('no-select'); // Prevent text selection while dragging
            e.stopPropagation();
        });
    }

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;

        // Calculate new width
        let newWidth = e.clientX;
        if (newWidth < 200) newWidth = 200;
        if (newWidth > 600) newWidth = 600;

        tocPane.style.width = `${newWidth}px`;
    });

    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            document.body.style.cursor = '';
            document.body.classList.remove('no-select');
            try {
                localStorage.setItem('tocWidth', tocPane.style.width);
            } catch (e) {
                // Ignore
            }
        }
    });

    // Restore width
    try {
        const savedWidth = localStorage.getItem('tocWidth');
        if (savedWidth) {
            tocPane.style.width = savedWidth;
        }
    } catch (e) {
        // Ignore
    }
});
