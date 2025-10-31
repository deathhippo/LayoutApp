document.addEventListener('DOMContentLoaded', () => {
    const loginModal = document.getElementById('login-modal');
    const mainContent = document.querySelector('main');
    const loginBtn = document.getElementById('login-btn');
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const loginError = document.getElementById('login-error');
    const logoutBtn = document.getElementById('logout-btn');

    async function fetchApi(endpoint, options = {}, isJson = true) {
        if (!options.method || options.method.toUpperCase() === 'GET') {
            options.cache = 'no-store';
        }
        try {
            const response = await fetch(endpoint, options);
            if (!response.ok) {
                if (response.status === 401) {
                    loginModal.classList.remove('hidden');
                    mainContent.classList.add('hidden');
                    loginError.textContent = 'Session expired. Please log in again.';
                }
                const errorBody = await response.json().catch(() => ({ message: `HTTP Error ${response.status}` }));
                throw new Error(errorBody.message || `API request failed`);
            }
            return isJson ? response.json() : response;
        } catch(e) {
            console.error("API Fetch Error:", e);
            throw e;
        }
    }

    async function attemptLogin() {
        loginError.textContent = '';
        loginBtn.disabled = true;
        loginBtn.textContent = 'Logging in...';
        try {
            const response = await fetchApi('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: usernameInput.value, password: passwordInput.value })
            });
            if (response.status === 'success') {
                loginModal.classList.add('hidden');
                mainContent.classList.remove('hidden');
                initializeApp(response.role, response.username);
            }
        } catch (error) {
            loginError.textContent = 'Invalid credentials.';
        } finally {
            loginBtn.disabled = false;
            loginBtn.textContent = 'Log In';
        }
    }

    loginBtn.addEventListener('click', attemptLogin);
    passwordInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') attemptLogin();
    });

    logoutBtn.addEventListener('click', () => {
        window.location.href = '/api/logout';
    });

    function initializeApp(userRole, currentUsername) {
        const canvasWrapper = document.getElementById('canvas-wrapper');
        const canvas = document.getElementById('layout-canvas');
        const overlayContainer = document.getElementById('overlay-container');
        const ctx = canvas.getContext('2d');
        const detailsPanel = document.getElementById('details-panel');
        const panelTitle = document.getElementById('panel-title');
        const panelContent = document.getElementById('panel-content');
        const panelFooter = document.getElementById('panel-footer');
        const panelCloseBtn = document.getElementById('panel-close-btn');
        const statusText = document.getElementById('status-text');
        const zoomLevelText = document.getElementById('zoom-level');
        const zoomInBtn = document.getElementById('zoom-in-btn');
        const zoomOutBtn = document.getElementById('zoom-out-btn');
        const addProjectBtn = document.getElementById('add-project-btn');
        const removeProjectBtn = document.getElementById('remove-project-btn');
        const moveProjectBtn = document.getElementById('move-project-btn');
        const photoUploadInput = document.getElementById('photo-upload-input');
        const imageViewerModal = document.getElementById('image-viewer-modal');
        const fullscreenImage = document.getElementById('fullscreen-image');
        const imageViewerCloseBtn = document.getElementById('image-viewer-close');
        const selectProjectModal = document.getElementById('select-project-modal');
        const selectModalCloseBtn = document.getElementById('select-modal-close-btn');
        const selectProjectDropdown = document.getElementById('select-project-dropdown');
        const selectModalAddBtn = document.getElementById('select-modal-add-btn');
        const searchInput = document.getElementById('search-input');
        const searchBtn = document.getElementById('search-btn');

        // --- NEW ELEMENT VARIABLES ---
        const myProjectsBtn = document.getElementById('my-projects-btn');
        const myProjectsModal = document.getElementById('my-projects-modal');
        const myProjectsModalCloseBtn = document.getElementById('my-projects-modal-close-btn');
        const myProjectsListContainer = document.getElementById('my-projects-list-container');
        // --- END NEW ELEMENT VARIABLES ---

        let lastData = null, imageCache = {}, viewTransform = { scale: 1, panX: 0, panY: 0 };
        let isPanning = false, panStart = { x: 0, y: 0 }, mouseDownPos = { x: 0, y: 0 };
        let isAddMode = false;
        let isRemoveMode = false;
        let isMoveMode = false;
        let draggedItem = null;
        let dragStartPos = { x: 0, y: 0 };
        let addCoordinates = { x: 0, y: 0 };
        const isAdmin = userRole === 'admin';
        let highlightedItemName = null;
        let highlightTimeout = null;

        if (isAdmin) {
            addProjectBtn.classList.remove('hidden');
            removeProjectBtn.classList.remove('hidden');
            moveProjectBtn.classList.remove('hidden');
        }

        function resizeCanvas() {
            const parent = canvas.parentElement;
            canvas.width = parent.clientWidth;
            canvas.height = parent.clientHeight;
            if (lastData) drawLayout();
        }

        function getWorldCoords(e) {
            const rect = canvas.getBoundingClientRect();
            const worldX = (e.clientX - rect.left - viewTransform.panX) / viewTransform.scale;
            const worldY = (e.clientY - rect.top - viewTransform.panY) / viewTransform.scale;
            return { worldX, worldY };
        }

        function findClickedItem(worldX, worldY) {
            return [...(lastData?.items || [])].reverse().find(i =>
                i.type === 'project' &&
                worldX >= i.x && worldX <= i.x + (i.width || 180) &&
                worldY >= i.y && worldY <= i.y + (i.height || 60)
            );
        }

        function drawLayout() {
            if (!lastData) return;
            ctx.save();
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.translate(viewTransform.panX, viewTransform.panY);
            ctx.scale(viewTransform.scale, viewTransform.scale);

            const bg = lastData.background;
            if (bg?.image_path && imageCache[bg.image_path]) {
                ctx.drawImage(imageCache[bg.image_path], bg.x, bg.y, bg.width, bg.height);
            }

            overlayContainer.innerHTML = '';
            lastData.items?.forEach(item => {
                if (item.type === 'project') {
                    drawProjectItem(item);
                    const canModify = isAdmin && (!item.owner || item.owner === currentUsername);
                    if (isRemoveMode && canModify) {
                        createRemoveOverlay(item);
                    }
                }
            });
            ctx.restore();
        }

        function createRemoveOverlay(item) {
                const { x, y, width = 180, height = 60 } = item;
                const overlay = document.createElement('div');
                overlay.className = 'project-item-overlay';
                overlay.style.position = 'absolute';
                overlay.style.transformOrigin = '0 0';
                overlay.style.transform = `translate(${viewTransform.panX + x * viewTransform.scale}px, ${viewTransform.panY + y * viewTransform.scale}px) scale(${viewTransform.scale})`;
                overlay.style.width = `${width}px`;
                overlay.style.height = `${height}px`;
                overlay.dataset.projectName = item.name;
                overlayContainer.appendChild(overlay);
        }

        function drawProjectItem(item) {
            const { x, y, width = 180, height = 60 } = item; // Reverted default size
            const scaled = {
                lineWidth: 1 / viewTransform.scale, borderRadius: 6 / viewTransform.scale, padding: 8 / viewTransform.scale,
                pBarHeight: 10 / viewTransform.scale, fontSize: 12 / viewTransform.scale, subFontSize: 10 / viewTransform.scale,
                iconSize: 16 / viewTransform.scale, iconPadding: 8 / viewTransform.scale, priorityDotSize: 5 / viewTransform.scale,
                ownerFontSize: 9 / viewTransform.scale
            };

            let fillColor = 'rgba(31, 41, 55, 0.9)';
            let strokeColor = '#4b5563';
            let strokeWidth = scaled.lineWidth;

            if (item.pause_status) {
                if (item.pause_status === 'Missing Parts') strokeColor = '#f97316';
                else strokeColor = '#ef4444';
                strokeWidth = 2.5 / viewTransform.scale;
            }

            if (isAdmin && item.owner && item.owner !== currentUsername) {
                fillColor = 'rgba(55, 65, 81, 0.8)';
            }

            if (item.name === highlightedItemName) {
                strokeColor = '#34d399'; // Emerald green for highlight
                strokeWidth = 3 / viewTransform.scale;
            }

            ctx.fillStyle = fillColor;
            ctx.strokeStyle = strokeColor;
            ctx.lineWidth = strokeWidth;
            ctx.beginPath();
            ctx.roundRect(x, y, width, height, scaled.borderRadius);
            ctx.fill();
            ctx.stroke();

            const pBarY = y + height - scaled.pBarHeight;
            ctx.fillStyle = 'rgba(17, 24, 39, 0.5)'; ctx.fillRect(x, pBarY, width, scaled.pBarHeight);
            if (item.status?.percentage > 0) {
                ctx.fillStyle = '#3b82f6'; ctx.fillRect(x, pBarY, width * (item.status.percentage / 100), scaled.pBarHeight);
            }

            ctx.textBaseline = 'top';
            ctx.fillStyle = 'white'; ctx.font = `600 ${scaled.fontSize}px Inter`; ctx.textAlign = 'left';

            const priorityColors = { 'Urgent': '#ef4444', 'High': '#f97316', 'Normal': '#3b82f6' };
            let textStartX = x + scaled.padding;
            if (item.priority && priorityColors[item.priority]) {
                ctx.fillStyle = priorityColors[item.priority];
                ctx.beginPath();
                ctx.arc(x + scaled.padding, y + scaled.padding + scaled.fontSize/2, scaled.priorityDotSize, 0, 2 * Math.PI);
                ctx.fill();
                textStartX += scaled.priorityDotSize * 2 + scaled.padding / 2;
            }
            ctx.fillStyle = 'white';
            ctx.fillText(item.name, textStartX, y + scaled.padding, width - (textStartX - x) - scaled.padding - (item.owner ? 45 : 40));

            if (item.owner) {
                ctx.font = `400 ${scaled.ownerFontSize}px Inter`;
                ctx.fillStyle = '#9ca3af';
                ctx.textAlign = 'right';
                 const ownerY = y + scaled.padding + scaled.fontSize * 1.2; // Adjusted Y slightly
                ctx.fillText(item.owner, x + width - scaled.padding, ownerY);
            }

             // Draw Status % (Above the thumbnail, black/green)
            if (item.status) {
                ctx.font = `700 ${scaled.fontSize * 1.1}px Inter`; // Slightly larger font
                ctx.fillStyle = item.status.percentage === 100 ? '#4ade80' : 'black'; // Black default, Green when 100%
                ctx.textAlign = 'center'; // Center the text
                ctx.textBaseline = 'bottom';
                ctx.fillText(`${item.status.percentage}%`, x + width / 2, y - scaled.padding * 0.5); // Position centered above
                ctx.textBaseline = 'top'; // Reset baseline
            }

            ctx.textAlign = 'left'; ctx.fillStyle = '#9ca3af'; ctx.font = `400 ${scaled.subFontSize}px Inter`;
             const workerY = y + scaled.padding + scaled.fontSize * 1.4; // Adjusted Y slightly
            ctx.fillText(`Worker: ${item.details || 'N/A'}`, x + scaled.padding, workerY, width - scaled.padding * 2);

            const iconsToShow = [];
            if (item.pause_status) {
                if (item.pause_status === 'Missing Parts') iconsToShow.push('missing_parts');
                else if (item.pause_status === 'Construction Error') iconsToShow.push('construction_error');
                else if (item.pause_status === 'Paused') iconsToShow.push('paused');
            }
            else if (item.packaging_status === 'Ready') { iconsToShow.push('box'); }
            else {
                if (item.electrification_status === 'Ready' && !item.electrification_completed_at) iconsToShow.push('bolt');
                if (item.control_status === 'Ready' && !item.control_completed_at) iconsToShow.push('check');
            }

            if (iconsToShow.length > 0) {
                const totalIconWidth = (iconsToShow.length * scaled.iconSize) + ((iconsToShow.length - 1) * scaled.iconPadding);
                let startX = x + (width / 2) - (totalIconWidth / 2);
                const iconY = y + height + scaled.padding;
                iconsToShow.forEach(iconType => {
                    if (iconType === 'bolt') drawBoltIcon(ctx, startX, iconY, scaled.iconSize);
                    if (iconType === 'check') drawCheckIcon(ctx, startX, iconY, scaled.iconSize, viewTransform.scale);
                    if (iconType === 'box') drawBoxIcon(ctx, startX, iconY, scaled.iconSize, viewTransform.scale);
                    if (iconType === 'missing_parts') drawMissingPartsIcon(ctx, startX, iconY, scaled.iconSize, viewTransform.scale);
                    if (iconType === 'construction_error') drawConstructionErrorIcon(ctx, startX, iconY, scaled.iconSize, viewTransform.scale);
                    if (iconType === 'paused') drawPausedIcon(ctx, startX, iconY, scaled.iconSize);
                    startX += scaled.iconSize + scaled.iconPadding;
                });
            }
        }

        function drawBoltIcon(ctx, x, y, size) {
            ctx.fillStyle = '#facc15'; ctx.beginPath();
            ctx.moveTo(x + size * 0.4, y); ctx.lineTo(x, y + size * 0.6); ctx.lineTo(x + size * 0.3, y + size * 0.6);
            ctx.lineTo(x + size * 0.2, y + size); ctx.lineTo(x + size, y + size * 0.4); ctx.lineTo(x + size * 0.7, y + size * 0.4);
            ctx.lineTo(x + size * 0.8, y);
            ctx.closePath(); ctx.fill();
        }
        function drawCheckIcon(ctx, x, y, size, scale) {
            ctx.strokeStyle = '#38bdf8'; ctx.lineWidth = 2.5 / scale; ctx.beginPath();
            ctx.moveTo(x + size * 0.1, y + size * 0.5); ctx.lineTo(x + size * 0.4, y + size * 0.9); ctx.lineTo(x + size * 0.9, y + size * 0.1);
            ctx.stroke();
        }
        function drawBoxIcon(ctx, x, y, size, scale) {
            ctx.strokeStyle = '#fb923c'; ctx.lineWidth = 1.5 / scale; ctx.strokeRect(x, y, size, size);
            ctx.beginPath(); ctx.moveTo(x, y + size * 0.3); ctx.lineTo(x + size, y + size * 0.3); ctx.stroke();
        }
        function drawMissingPartsIcon(ctx, x, y, size, scale) {
            ctx.strokeStyle = '#f97316'; ctx.lineWidth = 1.5 / scale; ctx.beginPath();
            ctx.arc(x + size * 0.4, y + size * 0.4, size * 0.35, 0, 2 * Math.PI); ctx.moveTo(x + size * 0.65, y + size * 0.65);
            ctx.lineTo(x + size * 0.9, y + size * 0.9); ctx.stroke();
        }
        function drawConstructionErrorIcon(ctx, x, y, size, scale) {
            ctx.strokeStyle = '#ef4444'; ctx.lineWidth = 1.5 / scale; ctx.beginPath();
            ctx.arc(x + size * 0.25, y + size * 0.25, size * 0.2, 0, 2 * Math.PI); ctx.moveTo(x + size * 0.4, y + size * 0.4);
            ctx.lineTo(x + size * 0.8, y + size * 0.8); ctx.moveTo(x + size * 0.6, y + size * 0.9); ctx.lineTo(x + size * 0.9, y + size * 0.6);
            ctx.stroke();
        }
        function drawPausedIcon(ctx, x, y, size) {
            ctx.fillStyle = '#ef4444'; ctx.fillRect(x + size * 0.2, y, size * 0.2, size); ctx.fillRect(x + size * 0.6, y, size * 0.2, size);
        }

        async function fetchAndDraw() {
            statusText.textContent = 'Syncing...';
            try {
                const data = await fetchApi('/api/layout_data');
                if (data?.background?.image_path && !imageCache[data.background.image_path]) {
                    const img = new Image();
                    img.src = `/api/get_image?path=${encodeURIComponent(data.background.image_path)}`;
                    await new Promise((resolve, reject) => {
                        img.onload = () => { imageCache[data.background.image_path] = img; resolve(); };
                        img.onerror = () => { imageCache[data.background.image_path] = null; reject('Image load failed'); };
                    });
                }
                lastData = data;
                drawLayout();
                if (!statusText.textContent.startsWith('Found:') && !statusText.textContent.startsWith('Project not found')) {
                     statusText.textContent = 'Live';
                }
            } catch (error) { statusText.textContent = `Error`; console.error(error); }
        }

        function updateZoom(factor, pivotX, pivotY) {
            const newScale = Math.max(0.1, Math.min(5, viewTransform.scale * factor));
            const worldX = (pivotX - viewTransform.panX) / viewTransform.scale;
            const worldY = (pivotY - viewTransform.panY) / viewTransform.scale;
            viewTransform.panX = pivotX - worldX * newScale;
            viewTransform.panY = pivotY - worldY * newScale;
            viewTransform.scale = newScale;
            if (lastData) drawLayout();
            zoomLevelText.textContent = `${Math.round(viewTransform.scale * 100)}%`;
        }

        function centerOnItem(item) {
            const itemWidth = item.width || 180; // Use original default
            const itemHeight = item.height || 60; // Use original default
            const itemCenterX = item.x + itemWidth / 2;
            const itemCenterY = item.y + itemHeight / 2;
            const targetScale = 1;
            const targetPanX = canvas.width / 2 - itemCenterX * targetScale;
            const targetPanY = canvas.height / 2 - itemCenterY * targetScale;

            viewTransform.scale = targetScale;
            viewTransform.panX = targetPanX;
            viewTransform.panY = targetPanY;

            highlightedItemName = item.name;
            clearTimeout(highlightTimeout);
            highlightTimeout = setTimeout(() => {
                highlightedItemName = null;
                drawLayout();
            }, 2000);

            zoomLevelText.textContent = `${Math.round(viewTransform.scale * 100)}%`;
            drawLayout();
        }


        function formatTimestamp(isoString) {
            if (!isoString) return 'N/A';
            try {
                const date = new Date(isoString);
                const day = String(date.getDate()).padStart(2, '0');
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const year = String(date.getFullYear()).slice(-2);
                const hours = String(date.getHours()).padStart(2, '0');
                const minutes = String(date.getMinutes()).padStart(2, '0');
                return `${day}.${month}.${year} ${hours}:${minutes}`;
            } catch (e) {
                console.error("Error formatting timestamp:", isoString, e);
                return 'Invalid Date';
            }
         }

        // --- UPDATED showDetailsPanel (removed invalid comments) ---
        async function showDetailsPanel(item) {
            panelTitle.textContent = item.name;
            panelContent.innerHTML = `<p class="text-gray-400">Loading details...</p>`
            panelFooter.innerHTML = '';
            panelFooter.classList.add('hidden');
            detailsPanel.classList.remove('translate-x-full');

            const canModifyItem = isAdmin && (!item.owner || item.owner === currentUsername);

            const workOrders = await fetchApi(`/api/project/${item.name}/work_orders`);

            const [extraDetails, missingParts, arrivedParts, photos] = await Promise.all([
                fetchApi(`/api/project/${item.name}/extra_details`),
                fetchApi(`/api/project/${item.name}/missing_parts`), // Still fetch for count
                fetchApi(`/api/project/${item.name}/arrived_parts`),
                fetchApi(`/api/project/${item.name}/photos`)
            ]);

            const isEleReady = item.electrification_status === 'Ready', isEleDone = !!item.electrification_completed_at;
            const isConReady = item.control_status === 'Ready', isConDone = !!item.control_completed_at;

            const electrifyActionHtml = canModifyItem ? (isEleDone ? `<div class="text-xs text-green-400">Electrification completed.</div>` : isEleReady ? `<button data-action="reset_electrification" class="w-full bg-yellow-600 hover:bg-yellow-700 text-white font-bold py-2 px-4 rounded-lg">Undo 'Ready'</button>` : `<button data-action="electrify" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 px-4 rounded-lg">Electrification Ready</button>`) : `<div class="text-xs text-gray-500">${isEleDone ? 'Electrification completed.' : isEleReady ? 'Electrification Ready' : 'Pending'}</div>`;
            const controlActionHtml = canModifyItem ? (isConDone ? `<div class="text-xs text-green-400">Control completed.</div>` : isConReady ? `<button data-action="reset_control" class="w-full bg-yellow-600 hover:bg-yellow-700 text-white font-bold py-2 px-4 rounded-lg">Undo 'Ready'</button>` : `<button data-action="control" class="w-full bg-sky-600 hover:bg-sky-700 text-white font-bold py-2 px-4 rounded-lg">Control Ready</button>`) : `<div class="text-xs text-gray-500">${isConDone ? 'Control completed.' : isConReady ? 'Control Ready' : 'Pending'}</div>`;

            const currentPauseStatus = item.pause_status || 'none';
            const pauseActionHtml = canModifyItem ? `
                <div class="mt-4 pt-4 border-t border-gray-700">
                    <label for="pause-status-select" class="block text-sm font-medium mb-1 text-yellow-400">Pause Status:</label>
                    <select id="pause-status-select" class="w-full bg-gray-700 text-white border border-gray-600 rounded-md py-1.5 px-2 text-sm focus:ring-yellow-500 focus:border-yellow-500">
                        <option value="none" ${currentPauseStatus === 'none' ? 'selected' : ''}>- Not Paused -</option>
                        <option value="Missing Parts" ${currentPauseStatus === 'Missing Parts' ? 'selected' : ''}>Missing Parts</option>
                        <option value="Construction Error" ${currentPauseStatus === 'Construction Error' ? 'selected' : ''}>Construction Error</option>
                        <option value="Paused" ${currentPauseStatus === 'Paused' ? 'selected' : ''}>Paused (Repair)</option>
                    </select>
                </div>
            ` : `<div class="text-xs text-gray-500 mt-2">Pause Status: ${item.pause_status || 'Not Paused'}</div>`;

            const eleCompletionHtml = canModifyItem ? (isEleDone ? `<div class="flex items-center justify-between"><span class="text-xs text-green-400"><strong>Done</strong> (${formatTimestamp(item.electrification_completed_at)})</span><button data-action="reset_electrification" class="text-xs text-red-500 hover:text-red-400">Undo</button></div>` : isEleReady ? `<label class="flex items-center cursor-pointer"><input type="checkbox" data-task-type="electrification" class="h-5 w-5 rounded"><span class="ml-2 text-xs">Mark as Done</span></label>` : `<span class="text-xs text-gray-500">Not ready to complete</span>`) : `<span class="text-xs ${isEleDone ? 'text-green-400' : 'text-gray-500'}">${isEleDone ? `Done (${formatTimestamp(item.electrification_completed_at)})` : isEleReady ? 'Ready' : 'Pending'}</span>`;
            const conCompletionHtml = canModifyItem ? (isConDone ? `<div class="flex items-center justify-between"><span class="text-xs text-green-400"><strong>Done</strong> (${formatTimestamp(item.control_completed_at)})</span><button data-action="reset_control" class="text-xs text-red-500 hover:text-red-400">Undo</button></div>` : isConReady ? `<label class="flex items-center cursor-pointer"><input type="checkbox" data-task-type="control" class="h-5 w-5 rounded"><span class="ml-2 text-xs">Mark as Done</span></label>` : `<span class="text-xs text-gray-500">Not ready to complete</span>`) : `<span class="text-xs ${isConDone ? 'text-green-400' : 'text-gray-500'}">${isConDone ? `Done (${formatTimestamp(item.control_completed_at)})` : isConReady ? 'Ready' : 'Pending'}</span>`;

            const photosHtml = photos.length > 0 ? photos.map(p => `
                <div class="relative group">
                    <img src="${p.url}" data-filename="${p.filename}" class="w-full h-20 object-cover rounded-md cursor-pointer">
                    ${canModifyItem ? `<button data-action="delete-photo" data-filename="${p.filename}" class="absolute top-1 right-1 bg-red-600 text-white rounded-full h-5 w-5 text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">&times;</button>` : ''}
                </div>`).join('') : '<p class="text-xs text-gray-400 col-span-3">No photos uploaded.</p>';

            const priorityHtml = canModifyItem ? `
                <select id="priority-select" class="w-full bg-gray-700 text-white border border-gray-600 rounded-md py-1.5 px-2 text-sm focus:ring-indigo-500 focus:border-indigo-500">
                    <option value="Low" ${item.priority === 'Low' || !item.priority ? 'selected' : ''}>Low</option>
                    <option value="Normal" ${item.priority === 'Normal' ? 'selected' : ''}>Normal</option>
                    <option value="High" ${item.priority === 'High' ? 'selected' : ''}>High</option>
                    <option value="Urgent" ${item.priority === 'Urgent' ? 'selected' : ''}>Urgent</option>
                </select>` : `<p class="text-sm">${item.priority || 'Normal'}</p>`;

            const projectInfoHtml = `
                <ul class="text-xs space-y-2">
                    ${item.status ? `<li><strong>Status:</strong> ${item.status.completed}/${item.status.total} (${item.status.percentage}%)</li>` : ''}
                    ${item.owner ? `<li><strong>Owner:</strong> ${item.owner}</li>` : ''}
                    ${canModifyItem ?
                        `<li>
                            <label for="worker-input" class="block font-bold">Worker(s):</label>
                            <input type="text" id="worker-input" class="w-full bg-gray-700 rounded p-1.5 text-xs mt-1" value="${item.details || ''}">
                            </li>` :
                        (item.details ? `<li><strong>Worker(s):</strong> ${item.details}</li>` : '')
                    }
                </ul>`;

            const workOrdersHtml = workOrders.length > 0 ? workOrders.map(wo => {
                const isDisabled = wo.completion_source === 'auto' || wo.completion_source === 'both';
                const disabledAttribute = isDisabled ? 'disabled' : '';
                const checkedAttribute = wo.is_completed ? 'checked' : '';
                const cursorClass = isDisabled ? 'cursor-not-allowed' : 'cursor-pointer';
                const labelClass = isDisabled ? 'text-gray-500' : '';

                return `<div class="flex items-center">
                            <input
                                type="checkbox"
                                id="dni-${wo.work_order_no}"
                                data-wo-desc="${wo.description.replace(/"/g, '&quot;')}"
                                ${checkedAttribute}
                                ${disabledAttribute}
                                class="h-4 w-4 rounded mr-2 ${cursorClass}">
                            <label
                                for="dni-${wo.work_order_no}"
                                class="truncate ${labelClass} ${cursorClass}">
                                ${wo.description} ${isDisabled ? '<span class="text-blue-400 text-[9px] ml-1">(Auto)</span>' : ''}
                            </label>
                        </div>`;
            }).join('') : '<p class="text-gray-400">No work orders.</p>';

            // Build the Parts Status Summary with the link/button
            const partsStatusSummaryHtml = `
                <div class="flex justify-between items-center">
                    <h4 class="font-bold text-red-400 text-xs mb-1">Missing Parts (${missingParts.length})</h4>
                    ${missingParts.length > 0 ?
                       `<a href="/parts/${item.name}" target="_blank" class="text-xs bg-blue-600 hover:bg-blue-700 text-white font-medium py-1 px-2 rounded-md transition-colors">
                           Details &rarr;
                        </a>` : ''
                    }
                </div>`;

            // Removed the invalid { /* ... */ } comments from this section
            panelContent.innerHTML = `
                <div class="space-y-4">
                    <div class="bg-gray-800 p-3 rounded-lg"><h3 class="font-bold text-base text-indigo-300 mb-2">Project Info</h3>${projectInfoHtml}</div>
                    <div class="bg-gray-800 p-3 rounded-lg"><h3 class="font-bold text-base text-indigo-300 mb-2">Priority</h3>${priorityHtml}</div>
                    <div class="bg-gray-800 p-3 rounded-lg">
                        <details>
                            <summary class="font-bold text-base text-indigo-300 cursor-pointer">Parts Status</summary>
                            <div class="mt-2 pt-2 border-t border-gray-700">
                                ${partsStatusSummaryHtml}
                                <div class="text-xs space-y-1 max-h-32 overflow-y-auto pr-2 mt-1">
                                    ${missingParts.length > 0 ? missingParts.map(part => `<div class="truncate" title="${part.description} (${part.item_no})">- ${part.description} (${part.item_no})</div>`).join('') : '<p class="text-gray-400">No missing parts.</p>'}
                                </div>
                                <h4 class="font-bold text-green-400 text-xs mb-1 mt-3">Arrived Parts (${arrivedParts.length})</h4>
                                <div class="text-xs space-y-1 max-h-32 overflow-y-auto pr-2">
                                    ${arrivedParts.length > 0 ? arrivedParts.map(part => `<div class="truncate" title="${part.part} (Loc: ${part.location})">- ${part.part} (Loc: ${part.location || 'N/A'})</div>`).join('') : '<p class="text-gray-400">No arrived parts.</p>'}
                                </div>
                            </div>
                        </details>
                    </div>
                    <div class="bg-gray-800 p-3 rounded-lg"><h3 class="font-bold text-base text-indigo-300 mb-2">Photos (${photos.length})</h3><div id="photos-gallery" class="grid grid-cols-3 gap-2 mb-2 max-h-48 overflow-y-auto">${photosHtml}</div>${canModifyItem ? `<button data-action="add-photo" class="w-full bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded-lg">Add Photo</button>` : ''}</div>
                    <div class="bg-gray-800 p-3 rounded-lg ${!isAdmin ? 'hidden' : ''}"><h3 class="font-bold text-base text-indigo-300 mb-3">Actions</h3><div class="space-y-2">${electrifyActionHtml}${controlActionHtml}${pauseActionHtml}</div></div>
                    <div class="bg-gray-800 p-3 rounded-lg"><h3 class="font-bold text-base text-indigo-300 mb-3">Completion Status</h3><div class="space-y-3"><div class="flex items-center justify-between"><span class="text-xs">Electrification:</span> ${eleCompletionHtml}</div><div class="flex items-center justify-between"><span class="text-xs">Control:</span> ${conCompletionHtml}</div></div></div>
                    <div class="bg-gray-800 p-3 rounded-lg"><h3 class="font-bold text-base text-indigo-300 mb-2">Work Orders (DNI)</h3><div id="dni-list" class="text-xs space-y-1 max-h-32 overflow-y-auto">${workOrdersHtml}</div></div>
                    <div class="bg-gray-800 p-3 rounded-lg"><h3 class="font-bold text-base text-indigo-300 mb-2">Notes</h3><div class="space-y-2"><div><label class="block font-bold mb-1 text-xs">General</label><textarea id="notes-general" ${!canModifyItem ? 'readonly' : ''} class="w-full bg-gray-700 rounded p-1.5 text-xs" rows="3">${extraDetails.notes.notes || ''}</textarea></div><div><label class="block font-bold mb-1 text-xs">Electrification</label><textarea id="notes-electrification" ${!canModifyItem ? 'readonly' : ''} class="w-full bg-gray-700 rounded p-1.5 text-xs" rows="3">${extraDetails.notes.electrification_notes || ''}</textarea></div><div><label class="block font-bold mb-1 text-xs">Control</label><textarea id="notes-control" ${!canModifyItem ? 'readonly' : ''} class="w-full bg-gray-700 rounded p-1.5 text-xs" rows="3">${extraDetails.notes.control_notes || ''}</textarea></div></div></div>
                </div>`;

            if (canModifyItem) {
                panelFooter.innerHTML = `<button data-action="save-changes" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-lg">Save Changes</button>`;
                panelFooter.classList.remove('hidden');
            } else {
                panelFooter.classList.add('hidden');
            }
        }
        // --- END showDetailsPanel ---


        function hideDetailsPanel() { detailsPanel.classList.add('translate-x-full'); }

        // --- NEW "MY PROJECTS" MODAL FUNCTIONS ---
        function closeMyProjectsModal() {
            myProjectsModal.classList.add('hidden');
            myProjectsModal.classList.remove('flex');
        }

        function openMyProjectsModal() {
            myProjectsModal.classList.remove('hidden');
            myProjectsModal.classList.add('flex');
            myProjectsListContainer.innerHTML = '<p class="text-gray-400">Loading projects...</p>';

            if (!lastData || !lastData.items) {
                myProjectsListContainer.innerHTML = '<p class="text-red-500">Could not load project data. Try again in a few seconds.</p>';
                return;
            }

            const myProjects = lastData.items.filter(item => item.type === 'project' && item.owner === currentUsername);

            if (myProjects.length === 0) {
                myProjectsListContainer.innerHTML = '<p class="text-gray-400">You do not own any projects in the layout.</p>';
                return;
            }

            // Create a list
            const ul = document.createElement('ul');
            ul.className = 'space-y-2';

            myProjects.sort((a, b) => a.name.localeCompare(b.name)); // Sort them alphabetically

            myProjects.forEach(item => {
                const li = document.createElement('li');
                li.innerHTML = `
                    <button data-project-name="${item.name}" class="w-full text-left bg-gray-700 hover:bg-gray-600 p-3 rounded-md transition-colors">
                        <span class="font-bold text-white">${item.name}</span>
                        <span class="text-xs text-gray-400 block">Worker: ${item.details || 'N/A'}</span>
                    </button>
                `;
                ul.appendChild(li);
            });

            myProjectsListContainer.innerHTML = ''; // Clear loading message
            myProjectsListContainer.appendChild(ul);
        }
        // --- END "MY PROJECTS" MODAL FUNCTIONS ---


        // ... (handlePanelClick, handleAdminAction, change listener, mode button listeners, updateEditModeUI, modal functions, overlay listener, pointer listeners, wheel/zoom listeners, photo upload listener, search functions remain the same) ...
        function handlePanelClick(event) {
            const target = event.target;
            const button = target.closest('button');
            const img = target.closest('img');
            const projectId = panelTitle.textContent;

            if (img && !button) {
                fullscreenImage.src = img.src;
                imageViewerModal.classList.remove('hidden');
                imageViewerModal.classList.add('flex');
                return;
            }

             // Handle specific non-data-action buttons like the back button if needed
            if (button && button.textContent.includes('Back')) { // Simple check
                window.history.back();
                return;
            }


            const currentItem = lastData?.items.find(i => i.name === projectId);
            const canModifyItem = isAdmin && currentItem && (!currentItem.owner || currentItem.owner === currentUsername);

            if (!button || !projectId) return;

            const action = button.dataset.action;
            const requiresModify = ['add-photo', 'delete-photo', 'save-changes', 'electrify', 'control', 'reset_electrification', 'reset_control'];

            if (requiresModify.includes(action) && !canModifyItem) {
                alert("Permission denied. You do not own this item.");
                return;
            }

            if (!action) return;

            handleAdminAction(action, button, projectId);
        }

        async function handleAdminAction(action, button, projectId) {
                const currentItem = lastData?.items.find(i => i.name === projectId);
                const canModifyItem = isAdmin && currentItem && (!currentItem.owner || currentItem.owner === currentUsername);
                const requiresModify = ['add-photo', 'delete-photo', 'save-changes', 'electrify', 'control', 'reset_electrification', 'reset_control'];
                if (requiresModify.includes(action) && !canModifyItem) {
                    console.warn("Attempted action without permission:", action, projectId);
                    return;
                }

            if (action === 'add-photo') { photoUploadInput.click(); return; }
            if (action === 'delete-photo') {
                const filename = button.dataset.filename;
                if (confirm(`Are you sure you want to delete this photo?`)) {
                    try {
                        await fetchApi(`/api/project/${projectId}/photo/${filename}`, { method: 'DELETE' });
                        const updatedItem = lastData.items.find(i => i.name === projectId);
                        if (updatedItem) await showDetailsPanel(updatedItem);
                    } catch (error) {
                            alert(`Error deleting photo: ${error.message}`);
                    }
                }
                return;
            }

            if (action !== 'save-changes') button.disabled = true;

            try {
                if (action === 'electrify' || action === 'control') {
                    await fetchApi(`/api/project/${projectId}/${action}`, { method: 'POST' });
                } else if (action === 'reset_electrification' || action === 'reset_control') {
                    await fetchApi(`/api/project/${projectId}/reset_task/${action.replace('reset_','' )}`, { method: 'POST' });
                } else if (action === 'save-changes') {
                    button.textContent = 'Saving...'; button.disabled = true;
                    await Promise.all([
                        fetchApi(`/api/project/${projectId}/details`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ details: document.getElementById('worker-input').value })
                        }),
                        fetchApi(`/api/project/${projectId}/notes`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note_type: 'notes', content: document.getElementById('notes-general').value }) }),
                        fetchApi(`/api/project/${projectId}/notes`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note_type: 'electrification_notes', content: document.getElementById('notes-electrification').value }) }),
                        fetchApi(`/api/project/${projectId}/notes`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note_type: 'control_notes', content: document.getElementById('notes-control').value }) })
                    ]);
                    button.textContent = 'Saved!';
                    if (lastData) {
                        const item = lastData.items.find(i => i.name === projectId);
                        if (item) item.details = document.getElementById('worker-input').value;
                    }
                    setTimeout(() => { button.textContent = 'Save Changes'; button.disabled = false; }, 2000);
                        return;
                }

                    await fetchAndDraw();
                    if (!detailsPanel.classList.contains('translate-x-full')) {
                    const refreshedItem = lastData.items.find(i => i.name === projectId);
                        if (refreshedItem) await showDetailsPanel(refreshedItem); else hideDetailsPanel();
                    }

            } catch (error) {
                console.error("Error performing action:", action, error);
                alert(`Error: ${error.message}`);
                if (action === 'save-changes') {
                        button.textContent = 'Error!';
                        setTimeout(() => { button.textContent = 'Save Changes'; button.disabled = false; }, 2000);
                } else {
                    button.disabled = false;
                }
                await fetchAndDraw();
                const errorItem = lastData?.items.find(i => i.name === projectId);
                if (errorItem && !detailsPanel.classList.contains('translate-x-full')) await showDetailsPanel(errorItem);

            }
        }

        panelContent.addEventListener('click', handlePanelClick);
        panelFooter.addEventListener('click', handlePanelClick);

        panelContent.addEventListener('change', async (event) => {
            const target = event.target;
            const projectId = panelTitle.textContent;
            const currentItem = lastData?.items.find(i => i.name === projectId);
            const canModifyItem = isAdmin && currentItem && (!currentItem.owner || currentItem.owner === currentUsername);

            if (target.id === 'priority-select') {
                 if (!canModifyItem) {
                    alert("Permission denied. You do not own this item."); target.value = currentItem?.priority || 'Low'; return;
                }
                await fetchApi(`/api/project/${projectId}/priority`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ priority: target.value })
                });
                await fetchAndDraw();
            }

            if (target.id === 'pause-status-select') {
                 if (!canModifyItem) {
                        alert("Permission denied. You do not own this item."); target.value = currentItem?.pause_status || 'none'; return;
                }
                const reason = target.value === 'none' ? null : target.value;
                await fetchApi(`/api/project/${projectId}/pause`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ reason: reason })
                });
                await fetchAndDraw();
                const updatedItem = lastData.items.find(i => i.name === projectId);
                if (updatedItem) await showDetailsPanel(updatedItem);
            }

            const checkbox = target.closest('input[type="checkbox"]');
            if (checkbox) {
                if (checkbox.disabled) {
                    return;
                }

                 if (!canModifyItem) {
                        alert("Permission denied. You do not own this item."); checkbox.checked = !checkbox.checked; return;
                }

                checkbox.disabled = true;
                try {
                    if (checkbox.id.startsWith('dni-')) {
                        await fetchApi(`/api/dni/${checkbox.id.replace('dni-', '')}/status`, {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ completed: checkbox.checked, project_task_no: projectId, description: checkbox.dataset.woDesc })
                        });
                    } else {
                        await fetchApi(`/api/project/${projectId}/complete/${checkbox.dataset.taskType}`, { method: 'POST' });
                    }
                    await fetchAndDraw();
                    const updatedItemAfterCheck = lastData.items.find(i => i.name === projectId);
                    if (updatedItemAfterCheck && !detailsPanel.classList.contains('translate-x-full')) {
                         await showDetailsPanel(updatedItemAfterCheck);
                    }

                } catch (e) {
                     alert(`Error updating status: ${e.message}`);
                    checkbox.checked = !checkbox.checked;
                    checkbox.disabled = false;

                }
            }
        });


        addProjectBtn.addEventListener('click', () => {
            isAddMode = !isAddMode;
            isRemoveMode = false;
            isMoveMode = false;
            updateEditModeUI();
            if (!isAddMode) hideDetailsPanel();
        });

        removeProjectBtn.addEventListener('click', () => {
            isRemoveMode = !isRemoveMode;
            isAddMode = false;
            isMoveMode = false;
            updateEditModeUI();
            if (!isRemoveMode) hideDetailsPanel();
        });

        moveProjectBtn.addEventListener('click', () => {
            isMoveMode = !isMoveMode;
            isAddMode = false;
            isRemoveMode = false;
            updateEditModeUI();
            if (!isMoveMode) hideDetailsPanel();
        });

        function updateEditModeUI() {
            canvasWrapper.classList.toggle('add-mode-active', isAddMode);
            canvasWrapper.classList.toggle('remove-mode-active', isRemoveMode);
            canvasWrapper.classList.toggle('move-mode-active', isMoveMode);

            addProjectBtn.textContent = isAddMode ? 'X' : '+';
            removeProjectBtn.textContent = isRemoveMode ? 'X' : '-';
            moveProjectBtn.textContent = isMoveMode ? 'X' : 'M';

            if (!isAddMode) addProjectBtn.style.backgroundColor = '';
            if (!isRemoveMode) removeProjectBtn.style.backgroundColor = '';
            if (!isMoveMode) moveProjectBtn.style.backgroundColor = '';

            overlayContainer.style.pointerEvents = isRemoveMode ? 'auto' : 'none';
            if (lastData) drawLayout();
        }

        async function openSelectProjectModal() {
            selectProjectModal.classList.remove('hidden');
            selectProjectModal.classList.add('flex');
            selectProjectDropdown.innerHTML = '<option>Loading available projects...</option>';

            try {
                const availableProjects = await fetchApi('/api/available_projects');
                selectProjectDropdown.innerHTML = '';
                if (availableProjects.length > 0) {
                    availableProjects.forEach(projName => {
                        const option = document.createElement('option');
                        option.value = projName;
                        option.textContent = projName;
                        selectProjectDropdown.appendChild(option);
                    });
                    selectModalAddBtn.disabled = false;
                } else {
                    selectProjectDropdown.innerHTML = '<option value="">No projects to add</option>';
                    selectModalAddBtn.disabled = true;
                }
            } catch (error) {
                selectProjectDropdown.innerHTML = '<option value="">Error loading projects</option>';
                selectModalAddBtn.disabled = true;
            }
        }

        function closeSelectProjectModal() {
            selectProjectModal.classList.add('hidden');
            selectProjectModal.classList.remove('flex');
            isAddMode = false;
            updateEditModeUI();
        }

        selectModalAddBtn.addEventListener('click', async () => {
            const selectedProject = selectProjectDropdown.value;
            if (!selectedProject) return;
            selectModalAddBtn.disabled = true;
            selectModalAddBtn.textContent = 'Adding...';
            try {
                await fetchApi('/api/add_project_to_layout', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ project_name: selectedProject, x: addCoordinates.x, y: addCoordinates.y })
                });
                await fetchAndDraw();
            } catch (error) {
                alert('Error adding project to layout: ' + error.message);
            } finally {
                selectModalAddBtn.disabled = false;
                selectModalAddBtn.textContent = 'Add Project to Layout';
                closeSelectProjectModal();
            }
        });

        selectModalCloseBtn.addEventListener('click', closeSelectProjectModal);

        overlayContainer.addEventListener('click', async (e) => {
                if (!isRemoveMode) return;
                const overlay = e.target.closest('.project-item-overlay');
                if (overlay) {
                    e.stopPropagation();
                    const projectName = overlay.dataset.projectName;
                    const item = lastData?.items.find(i => i.name === projectName);
                    const canModify = isAdmin && item && (!item.owner || item.owner === currentUsername);
                    if (!canModify) {
                        alert("Permission denied. You do not own this item.");
                        return;
                    }

                    if (confirm(`Are you sure you want to remove ${projectName} from the layout?`)) {
                        try {
                            await fetchApi(`/api/remove_project_from_layout/${projectName}`, { method: 'DELETE' });
                            await fetchAndDraw();
                        } catch(error) {
                            alert(`Error removing project: ${error.message}`);
                        } finally {
                            isRemoveMode = false;
                            updateEditModeUI();
                        }
                    } else {
                        isRemoveMode = false;
                        updateEditModeUI();
                    }
                }
        });

        canvas.addEventListener('pointerdown', e => {
            const { worldX, worldY } = getWorldCoords(e);

            if (isMoveMode) {
                const clickedItem = findClickedItem(worldX, worldY);
                const canModify = clickedItem && isAdmin && (!clickedItem.owner || clickedItem.owner === currentUsername);
                if (canModify) {
                    draggedItem = clickedItem;
                    dragStartPos = { x: worldX - draggedItem.x, y: worldY - draggedItem.y };
                    isPanning = false;
                    canvas.style.cursor = 'grabbing';
                } else if (clickedItem) {
                    console.log("Cannot move item owned by", clickedItem.owner);
                    isPanning = true;
                    mouseDownPos = { x: e.clientX, y: e.clientY };
                    panStart = { x: e.clientX - viewTransform.panX, y: e.clientY - viewTransform.panY };
                } else {
                    isPanning = true;
                    mouseDownPos = { x: e.clientX, y: e.clientY };
                    panStart = { x: e.clientX - viewTransform.panX, y: e.clientY - viewTransform.panY };
                }
                return;
            }

            if (isAddMode || isRemoveMode) return;

            isPanning = true;
            mouseDownPos = { x: e.clientX, y: e.clientY };
            panStart = { x: e.clientX - viewTransform.panX, y: e.clientY - viewTransform.panY };
        });

        canvas.addEventListener('pointermove', e => {
                if (draggedItem) {
                const { worldX, worldY } = getWorldCoords(e);
                draggedItem.x = worldX - dragStartPos.x;
                draggedItem.y = worldY - dragStartPos.y;
                if (lastData) drawLayout();
                } else if (isPanning) {
                viewTransform.panX = e.clientX - panStart.x;
                viewTransform.panY = e.clientY - panStart.y;
                if (lastData) drawLayout();
                }
        });

        canvas.addEventListener('pointerup', async e => {
                if (draggedItem) {
                canvas.style.cursor = '';
                try {
                    await fetchApi('/api/move_project_to_layout', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            project_name: draggedItem.name,
                            x: draggedItem.x,
                            y: draggedItem.y
                        })
                    });
                } catch (error) {
                        alert('Error saving new position: ' + error.message);
                    await fetchAndDraw();
                } finally {
                    draggedItem = null;
                    isPanning = false;
                }
                return;
                }

                const wasPanning = isPanning;
                isPanning = false;
                const movedSignificantly = Math.abs(e.clientX - mouseDownPos.x) >= 5 || Math.abs(e.clientY - mouseDownPos.y) >= 5;

                if (wasPanning && movedSignificantly) return;
                if (isRemoveMode) return;
                if (isMoveMode) return;

                const { worldX, worldY } = getWorldCoords(e);

                if (isAddMode) {
                addCoordinates = { x: worldX, y: worldY };
                openSelectProjectModal();
                } else {
                const clickedItem = findClickedItem(worldX, worldY);
                if (clickedItem) {
                    showDetailsPanel(clickedItem);
                } else {
                    hideDetailsPanel();
                }
                }
        });

        canvas.addEventListener('wheel', e => { e.preventDefault(); const rect = canvas.getBoundingClientRect(); updateZoom(e.deltaY < 0 ? 1.1 : 1 / 1.1, e.clientX - rect.left, e.clientY - rect.top); });
        zoomInBtn.addEventListener('click', () => updateZoom(1.2, canvas.width / 2, canvas.height / 2));
        zoomOutBtn.addEventListener('click', () => updateZoom(1 / 1.2, canvas.width / 2, canvas.height / 2));
        panelCloseBtn.addEventListener('click', hideDetailsPanel);
        imageViewerCloseBtn.addEventListener('click', () => { imageViewerModal.classList.add('hidden'); imageViewerModal.classList.remove('flex'); });

        photoUploadInput.addEventListener('change', async (event) => {
                const file = event.target.files[0];
                const projectId = panelTitle.textContent;
                if (!file || !projectId) return;
                const currentItem = lastData?.items.find(i => i.name === projectId);
                const canModifyItem = isAdmin && currentItem && (!currentItem.owner || currentItem.owner === currentUsername);
                if (!canModifyItem) {
                        alert("Permission denied. You do not own this item.");
                        event.target.value = '';
                        return;
                }

                const addPhotoButton = panelContent.querySelector('button[data-action="add-photo"]');
                const originalText = addPhotoButton.textContent;
                addPhotoButton.textContent = 'Uploading...'; addPhotoButton.disabled = true;

                const formData = new FormData();
                formData.append('photo', file);

                try {
                await fetchApi(`/api/project/${projectId}/upload`, { method: 'POST', body: formData }, false);
                const updatedItem = lastData.items.find(i => i.name === projectId);
                if (updatedItem) await showDetailsPanel(updatedItem);
                } catch (error) {
                console.error('Upload failed:', error);
                alert(`Upload failed: ${error.message}`);
                addPhotoButton.textContent = 'Upload Failed!';
                setTimeout(() => { addPhotoButton.textContent = originalText; }, 2000);
                } finally {
                addPhotoButton.disabled = false;
                event.target.value = '';
                }
        });

        function performSearch() {
            const searchTerm = searchInput.value.trim().toLowerCase();
            if (!searchTerm || !lastData || !lastData.items) {
                if (statusText.textContent.startsWith('Found:') || statusText.textContent.startsWith('Project not found')) {
                    statusText.textContent = 'Live';
                }
                highlightedItemName = null;
                clearTimeout(highlightTimeout);
                drawLayout();
                return;
            }

            const foundItem = lastData.items.find(item =>
                item.type === 'project' &&
                item.name.toLowerCase().includes(searchTerm)
            );

            if (foundItem) {
                centerOnItem(foundItem);
                showDetailsPanel(foundItem);
                statusText.textContent = `Found: ${foundItem.name}`;
                searchInput.value = '';
            } else {
                statusText.textContent = 'Project not found';
                highlightedItemName = null;
                clearTimeout(highlightTimeout);
                drawLayout();
            }
        }
        searchBtn.addEventListener('click', performSearch);
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                performSearch();
            }
        });

        // --- NEW EVENT LISTENERS ---
        myProjectsBtn.addEventListener('click', openMyProjectsModal);
        myProjectsModalCloseBtn.addEventListener('click', closeMyProjectsModal);

        // Add click listener for the project list (event delegation)
        myProjectsListContainer.addEventListener('click', (e) => {
            const button = e.target.closest('button[data-project-name]');
            if (!button) return;

            const projectName = button.dataset.projectName;
            const item = lastData?.items.find(i => i.name === projectName);

            if (item) {
                closeMyProjectsModal();
                centerOnItem(item); // Center and highlight
                showDetailsPanel(item); // Open details
            } else {
                console.error('Could not find project item:', projectName);
                alert('Error: Could not find that project.');
            }
        });
        // --- END NEW EVENT LISTENERS ---


        // --- Initial setup ---
        window.addEventListener('resize', resizeCanvas);
        resizeCanvas();
        fetchAndDraw();
        setInterval(fetchAndDraw, 10000); // Refresh data every 10 seconds
    }

});