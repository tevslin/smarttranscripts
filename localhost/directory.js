/**
 * directory.js
 * Shared logic for discovering and rendering the meeting directory.
 */

export async function initializeDirectory(container, options = {}) {
    const {
        isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1',
        meetingsRoot = '/meetings/', // Default to absolute path
        s3IndexUrl = '/meetings/meetings_index.json',
        onLinkClick = null, // Callback: (event, path) => { ... }
        linkHrefGenerator = (path) => path, // Function: (path) => string
        activePath = null // The path of the current page, to highlight it
    } = options;

    let hierarchy = {};

    try {
        if (isLocal) {
            console.log("Directory: Running in LOCAL mode.");
            const paths = await discoverMeetingsLocal(meetingsRoot);
            hierarchy = buildHierarchyFromPaths(paths);
        } else {
            console.log("Directory: Running in S3 mode.");
            hierarchy = await discoverMeetingsS3(s3IndexUrl);
        }

        renderDirectory(hierarchy, container, linkHrefGenerator, onLinkClick, activePath);
        restoreDirectoryState();

    } catch (error) {
        console.error("Directory initialization failed:", error);
        container.innerHTML = '<li>Error loading meetings.</li>';
    }
}

async function discoverMeetingsLocal(baseUrl) {
    // Ensure baseUrl ends with /
    if (!baseUrl.endsWith('/')) baseUrl += '/';

    try {
        const response = await fetch(baseUrl);
        const htmlString = await response.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(htmlString, 'text/html');
        const links = Array.from(doc.querySelectorAll('a'));

        const promises = links.map(link => {
            const href = link.getAttribute('href');
            const text = link.textContent;

            // Ignore parent directory links and non-relative links
            if (text === '../' || href.startsWith('/') || href.includes(':')) return Promise.resolve([]);

            const fullPath = `${baseUrl}${href}`;

            if (text.endsWith('/')) {
                return discoverMeetingsLocal(fullPath);
            } else if (text === 'transcript.html') {
                return Promise.resolve([fullPath]);
            }
            return Promise.resolve([]);
        });

        const results = await Promise.all(promises);
        return results.flat();
    } catch (e) {
        console.warn(`Failed to fetch ${baseUrl}:`, e);
        return [];
    }
}

async function discoverMeetingsS3(indexUrl) {
    const response = await fetch(indexUrl);
    const data = await response.json();
    if (Array.isArray(data)) {
        return buildHierarchyFromPaths(data);
    }
    return data;
}

function buildHierarchyFromPaths(paths) {
    const root = { name: "root", type: "folder", children: {} };

    paths.forEach(fullPath => {
        // Remove leading slash
        const cleanPath = fullPath.startsWith('/') ? fullPath.substring(1) : fullPath;
        const parts = cleanPath.split('/').filter(p => p);

        // Skip "meetings" if it's the first part
        const relevantParts = parts[0] === 'meetings' ? parts.slice(1) : parts;

        let currentNode = root;

        relevantParts.forEach((part, index) => {
            const isLast = index === relevantParts.length - 1;

            if (isLast && part === 'transcript.html') {
                // This path ends in transcript.html. 
                // The CURRENT node (parent of this part) is the meeting folder.
                currentNode.isMeeting = true;
                currentNode.linkPath = fullPath;
                // We do NOT add transcript.html as a child.
            } else {
                // It's a folder or a file not named transcript.html
                if (!currentNode.children[part]) {
                    currentNode.children[part] = {
                        name: part,
                        type: "folder",
                        children: {}
                    };
                }
                currentNode = currentNode.children[part];
            }
        });
    });

    return root;
}

function renderDirectory(rootNode, container, linkHrefGenerator, onLinkClick, activePath) {
    container.innerHTML = '';
    const ul = document.createElement('ul');
    ul.className = 'toc-list';

    const sortChildren = (children) => {
        return Object.values(children).sort((a, b) => {
            return a.name.localeCompare(b.name);
        });
    };

    const buildTree = (node, parentElement) => {
        const sortedNodes = sortChildren(node.children);

        sortedNodes.forEach(child => {
            const li = document.createElement('li');

            if (child.isMeeting) {
                // It is a meeting folder. Render as a link item with folder icon.
                li.className = 'toc-item';

                const a = document.createElement('a');
                a.className = 'toc-link';
                a.href = linkHrefGenerator(child.linkPath);
                a.dataset.path = child.linkPath;

                // Add spacer to align with folders that have toggles
                const spacer = document.createElement('span');
                spacer.className = 'toc-toggle-spacer';
                a.appendChild(spacer);

                const icon = document.createElement('span');
                icon.className = 'toc-icon folder-icon';
                // icon.textContent = '📁'; 

                const text = document.createElement('span');
                text.className = 'toc-text';
                text.textContent = child.name.replace(/_/g, ' ');

                a.appendChild(icon);
                a.appendChild(text);
                li.appendChild(a);

                if (activePath && child.linkPath === activePath) {
                    a.classList.add('active-meeting');
                    // Expand parents
                    let parent = li.parentElement;
                    while (parent && parent !== container) {
                        if (parent.classList.contains('nested')) {
                            parent.classList.add('active');
                            const folderLi = parent.parentElement;
                            const toggle = folderLi.querySelector('.toc-toggle');
                            if (toggle) toggle.classList.add('open');
                        }
                        parent = parent.parentElement;
                    }
                }

                if (onLinkClick) {
                    a.addEventListener('click', (e) => {
                        onLinkClick(e, child.linkPath);
                    });
                }

                parentElement.appendChild(li);

            } else {
                // Regular folder
                li.className = 'toc-folder';

                const row = document.createElement('div');
                row.className = 'toc-folder-row';

                const toggle = document.createElement('span');
                toggle.className = 'toc-toggle';

                const icon = document.createElement('span');
                icon.className = 'toc-icon folder-icon';

                const label = document.createElement('span');
                label.className = 'toc-label';
                label.textContent = child.name.replace(/_/g, ' ');

                row.appendChild(toggle);
                row.appendChild(icon);
                row.appendChild(label);
                li.appendChild(row);

                const nestedUl = document.createElement('ul');
                nestedUl.className = 'nested';
                li.appendChild(nestedUl);

                buildTree(child, nestedUl);

                parentElement.appendChild(li);
            }
        });
    };

    buildTree(rootNode, ul);
    container.appendChild(ul);

    // Event Delegation for Toggles
    container.addEventListener('click', (e) => {
        const folderRow = e.target.closest('.toc-folder-row');
        if (folderRow) {
            const li = folderRow.parentElement;
            const nested = li.querySelector('.nested');
            const toggle = folderRow.querySelector('.toc-toggle');

            if (nested) {
                nested.classList.toggle('active');
                toggle.classList.toggle('open');
                saveDirectoryState();
            }
        }
    });
}

function saveDirectoryState() {
    const state = {};
    document.querySelectorAll('.toc-folder').forEach((folder, index) => {
        const toggle = folder.querySelector('.toc-toggle');
        if (toggle && toggle.classList.contains('open')) {
            state[index] = true;
        }
    });
    localStorage.setItem('directoryState', JSON.stringify(state));
}

function restoreDirectoryState() {
    const state = JSON.parse(localStorage.getItem('directoryState')) || {};
    document.querySelectorAll('.toc-folder').forEach((folder, index) => {
        if (state[index]) {
            const toggle = folder.querySelector('.toc-toggle');
            const nested = folder.querySelector('.nested');
            if (toggle) toggle.classList.add('open');
            if (nested) nested.classList.add('active');
        }
    });
}
