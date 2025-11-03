document.addEventListener('DOMContentLoaded', () => {
    const meetingListContainer = document.getElementById('meeting-list-container');
    const meetingList = document.getElementById('meeting-list');
    const agendaDisplay = document.getElementById('agenda-display');
    const agendaTitle = document.getElementById('agenda-title');
    const agendaItems = document.getElementById('agenda-items');
    const openTranscriptButton = document.getElementById('open-transcript-button');
    const openOfficialTranscriptButton = document.getElementById('open-official-transcript-button');

    const agendaPlaceholder = document.getElementById('agenda-placeholder');
    const agendaContent = document.getElementById('agenda-content');

    let allMeetings = [];

    // --- 1. Discovery ---
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

    if (isLocal) {
        console.log("Running in LOCAL mode.");
        discoverMeetingsLocal('meetings/').then(paths => {
            const hierarchy = buildHierarchyFromPaths(paths);
            processHierarchy(hierarchy);
        });
    } else {
        console.log("Running in S3 mode.");
        discoverMeetingsS3();
    }

    function discoverMeetingsLocal(baseUrl) {
        return fetch(baseUrl)
            .then(response => response.text())
            .then(htmlString => {
                const parser = new DOMParser();
                const doc = parser.parseFromString(htmlString, 'text/html');
                const links = Array.from(doc.querySelectorAll('a'));
                
                const promises = links.map(link => {
                    const href = link.getAttribute('href');
                    const text = link.textContent;
                    const fullPath = `${baseUrl}${href}`;

                    if (text.endsWith('/') && !text.startsWith('../')) {
                        return discoverMeetingsLocal(fullPath);
                    } else if (text === 'transcript.html') {
                        return Promise.resolve([fullPath]);
                    }
                    return Promise.resolve([]);
                });

                return Promise.all(promises).then(results => results.flat());
            });
    }

    function discoverMeetingsS3() {
        fetch('/meetings/meetings_index.json')
            .then(response => response.json())
            .then(hierarchy => {
                processHierarchy(hierarchy);
            })
            .catch(error => {
                console.error("Error fetching meetings index:", error);
                meetingList.innerHTML = '<li>Error loading meetings. Please try again later.</li>';
            });
    }
    
    function buildHierarchyFromPaths(paths) {
        const hierarchy = {};
        paths.forEach(fullPath => {
            const relativePath = fullPath.startsWith('meetings/') ? fullPath.substring(9) : fullPath;
            const parts = relativePath.split('/').filter(p => p && p !== 'transcript.html');
            
            if (parts.length < 2) return;

            const committee = parts[0];
            let subcommittee = 'Full_Board';
            let meeting;

            if (parts.length === 2) {
                meeting = parts[1];
            } else {
                subcommittee = parts[1];
                meeting = parts[2];
            }

            if (!hierarchy[committee]) hierarchy[committee] = {};
            if (!hierarchy[committee][subcommittee]) hierarchy[committee][subcommittee] = [];
            
            hierarchy[committee][subcommittee].push({ name: meeting, path: fullPath });
        });
        return hierarchy;
    }

    function processHierarchy(hierarchy) {
        allMeetings = flattenHierarchy(hierarchy);
        renderDirectory(hierarchy, meetingList);
        restoreDirectoryState();
    }
    
    function flattenHierarchy(hierarchy) {
        const flatList = [];
        for (const committee in hierarchy) {
            for (const subcommittee in hierarchy[committee]) {
                hierarchy[committee][subcommittee].forEach(meeting => {
                    const title = `${committee.replace(/_/g, ' ')} - ${subcommittee.replace(/_/g, ' ')} - ${meeting.name.replace(/_/g, ' ')}`;
                    flatList.push({ ...meeting, displayTitle: title });
                });
            }
        }
        return flatList;
    }

    // --- 2. Rendering ---
    function renderDirectory(hierarchy, container) {
        container.innerHTML = '';
        const sortedCommittees = Object.keys(hierarchy).sort();

        sortedCommittees.forEach(committeeName => {
            const committeeLi = createCollapsibleList(committeeName.replace(/_/g, ' '));
            container.appendChild(committeeLi);

            const sortedSubcommittees = Object.keys(hierarchy[committeeName]).sort();
            sortedSubcommittees.forEach(subcommitteeName => {
                const subcommitteeLi = createCollapsibleList(subcommitteeName.replace(/_/g, ' '));
                committeeLi.querySelector('.nested').appendChild(subcommitteeLi);

                const meetings = hierarchy[committeeName][subcommitteeName];
                meetings.sort((a, b) => b.name.localeCompare(a.name));
                
                meetings.forEach(meeting => {
                    const meetingLi = document.createElement('li');
                    const meetingLink = document.createElement('a');
                    meetingLink.href = '#';
                    meetingLink.textContent = meeting.name.replace(/_/g, ' ');
                    meetingLink.dataset.path = meeting.path;
                    meetingLi.appendChild(meetingLink);
                    subcommitteeLi.querySelector('.nested').appendChild(meetingLi);
                });
            });
        });
    }

    function createCollapsibleList(name) {
        const li = document.createElement('li');
        li.innerHTML = `<span class="caret">${name}</span><ul class="nested"></ul>`;
        return li;
    }

    // --- 3. Event Handling ---
    meetingListContainer.addEventListener('click', (e) => {
        if (e.target.classList.contains('caret')) {
            e.target.parentElement.querySelector('.nested').classList.toggle('active');
            e.target.classList.toggle('caret-down');
            saveDirectoryState();
        }
        if (e.target.tagName === 'A') {
            e.preventDefault();
            displayMeetingDetails(e.target.dataset.path);
        }
    });
    
    function displayMeetingDetails(filePath) {
        openTranscriptButton.dataset.path = filePath;
        
        fetch(filePath)
            .then(response => response.text())
            .then(htmlString => {
                const parser = new DOMParser();
                const doc = parser.parseFromString(htmlString, 'text/html');
                
                const title = doc.querySelector('#meeting-title').textContent;
                const agendaHtml = doc.querySelector('#agenda ul').innerHTML;
                const officialTranscriptLink = doc.querySelector('a[href*="official-transcript"]');

                agendaTitle.textContent = title;
                agendaItems.innerHTML = agendaHtml;

                agendaItems.querySelectorAll('a').forEach(a => {
                    const originalHref = a.getAttribute('href');
                    const anchor = originalHref.substring(1);
                    a.href = `${filePath.replace('transcript.html', '')}transcript.html?agenda=${anchor}`;
                    a.target = '_blank';
                });

                if (officialTranscriptLink) {
                    openOfficialTranscriptButton.href = officialTranscriptLink.href;
                    openOfficialTranscriptButton.style.display = 'inline-block';
                } else {
                    openOfficialTranscriptButton.style.display = 'none';
                }

                agendaPlaceholder.style.display = 'none';
                agendaContent.style.display = 'block';
            });
    }
    
    openTranscriptButton.addEventListener('click', (e) => {
        window.open(e.target.dataset.path, '_blank');
    });

    // --- 4. State Persistence ---
    function saveDirectoryState() {
        const state = {};
        document.querySelectorAll('.caret').forEach((caret, index) => {
            if (caret.classList.contains('caret-down')) {
                state[index] = true;
            }
        });
        localStorage.setItem('directoryState', JSON.stringify(state));
    }

    function restoreDirectoryState() {
        const state = JSON.parse(localStorage.getItem('directoryState')) || {};
        document.querySelectorAll('.caret').forEach((caret, index) => {
            if (state[index]) {
                caret.classList.add('caret-down');
                caret.parentElement.querySelector('.nested').classList.add('active');
            }
        });
    }
});