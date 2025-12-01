
import { initializeDirectory } from './directory.js';

document.addEventListener('DOMContentLoaded', () => {
    const tocPane = document.getElementById('toc-pane');
    const tocContent = document.getElementById('toc-content');
    const pinButton = document.getElementById('toc-pin-button');
    const resizeHandle = document.getElementById('toc-resize-handle');

    if (!tocPane || !tocContent) return;

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
        // Insert wrapper into pane (resize handle stays outside or append it back?)
        // Resize handle should probably be outside wrapper if it resizes the pane width.
        // But if unpinned, resize handle might be hidden or part of flyout?
        // Let's keep resize handle as direct child of pane for now.
        tocPane.insertBefore(tocWrapper, resizeHandle);
    }

    initializeDirectory(document.getElementById('toc-content'), {
        activePath: window.location.pathname,
        linkHrefGenerator: (path) => path // Use the absolute path directly
    });

    // --- Pinning Logic ---
    // Default to pinned (true) if not set
    let savedState = null;
    try {
        savedState = localStorage.getItem('tocPinned');
    } catch (e) {
        console.warn('localStorage not accessible:', e);
    }
    let isPinned = savedState === null ? true : savedState === 'true';

    // Check if we are on index.html or root
    const isIndexPage = window.location.pathname.endsWith('index.html') || window.location.pathname === '/';

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

        // Only save state if NOT on index page, to avoid overwriting user preference with forced state
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
    // It does NOT pin it back.

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
