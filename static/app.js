const outagesTableBody = document.querySelector('#outagesTable tbody');
const resetBtn = document.getElementById("resetBtn"); 
const checkMyAreaBtn = document.getElementById("checkMyAreaBtn"); 
const statusBar = document.getElementById("localStatusMessage");
const emptyMessage = document.getElementById("emptyMessage");
const searchInput = document.getElementById('outageSearch'); 

let outagesData = [];
const R = 6371; // Earth's radius in km

/**
 * Highlights search matches within text using spans
 */
function highlightMatch(text, filter) {
    if (!filter) return text;
    const escapedFilter = filter.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedFilter})`, 'gi');
    return text.replace(regex, '<span class="highlight">$1</span>');
}

/**
 * Distance Calculation using Haversine Formula
 */
function haversine_distance(lat1, lon1, lat2, lon2) {
    const dLat = (lat2 - lat1) * (Math.PI / 180);
    const dLon = (lon2 - lon1) * (Math.PI / 180);
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) + 
              Math.cos(lat1 * (Math.PI / 180)) * Math.cos(lat2 * (Math.PI / 180)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

/**
 * Renders the outages table with color-coding and icons
 */
function fillTable(outagesToDisplay, currentFilter = '') {
    outagesTableBody.innerHTML = '';
    const filterText = currentFilter.trim();
    const shouldExpand = filterText.length > 0;

    if (!outagesToDisplay || !Array.isArray(outagesToDisplay) || outagesToDisplay.length === 0) {
        emptyMessage.style.display = 'block';
        return;
    }

    emptyMessage.style.display = 'none';

    // Sort by date descending (Newest first)
    outagesToDisplay.sort((a, b) => new Date(b.date) - new Date(a.date));

    outagesToDisplay.forEach(outage => {
        try {
            const row = outagesTableBody.insertRow();
            
            // 1. Date Status Logic (Imminent vs Past)
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const outageDate = new Date(outage.date);
            outageDate.setHours(0, 0, 0, 0);

            if (outageDate >= today) {
                row.classList.add('outage-imminent');
            } else {
                row.classList.add('outage-past');
            }

            // 2. Distance Logic
            let distanceHtml = '';
            if (outage.distance_km) {
                const dist = parseFloat(outage.distance_km).toFixed(1);
                distanceHtml = `<br><strong class="dist-tag"><i class="fas fa-location-dot"></i> ${dist} km away</strong>`;
            }

            // 3. Cell 1: District & Distance
            const highlightedArea = highlightMatch(outage.area || "Unknown Area", filterText);
            const areaCell = row.insertCell();
            areaCell.innerHTML = `<strong>${highlightedArea}</strong>${distanceHtml}`; 

            // 4. Cell 2: Date
            const dateCell = row.insertCell();
            dateCell.innerHTML = `<i class="far fa-calendar-alt"></i> ${outage.date || 'TBD'}`;

            // 5. Cell 3: Time
            const timeCell = row.insertCell();
            timeCell.innerHTML = `<i class="far fa-clock"></i> ${outage.time || 'TBD'}`;

            // 6. Cell 4: Sub-Areas with Details Toggle
            let subAreasArray = [];
            if (Array.isArray(outage.sub_areas)) {
                subAreasArray = outage.sub_areas;
            } else if (typeof outage.sub_areas === 'string') {
                subAreasArray = outage.sub_areas.split(',').map(s => s.trim());
            }
            
            const subAreasText = subAreasArray.join(', ');
            const highlightedSubAreas = highlightMatch(subAreasText, filterText);
            const detailsOpenAttribute = shouldExpand ? 'open' : '';

            const subAreaCell = row.insertCell();
            subAreaCell.innerHTML = `
                <details ${detailsOpenAttribute}>
                    <summary>View Locations</summary>
                    <p>${highlightedSubAreas || "No specific sub-areas listed"}</p>   
                </details>`;

        } catch (e) {
            console.error("Error rendering row:", e);
        }
    });
}

/**
 * Client-side search filtering logic
 */
function getFilteredOutages(filterText) {
    const filter = filterText.trim().toUpperCase();

    if (!filter) {
        fillTable(outagesData, filterText); 
        return;
    }

    const filteredData = outagesData.filter(outage => {
        const areaMatch = (outage.area || "").toUpperCase().includes(filter);
        const subAreaMatch = Array.isArray(outage.sub_areas) && outage.sub_areas.some(subArea => 
            subArea.toUpperCase().includes(filter)
        );
        return areaMatch || subAreaMatch;
    });

    fillTable(filteredData, filterText);
}

/**
 * Fetches proximity-filtered outages from API
 */
async function check_outages(lat, lon) {
    statusBar.textContent = "Calculating nearby outages...";
    try {
        let response = await fetch(`/api/check_outage?lat=${lat}&lon=${lon}`);
        
        if (!response.ok) throw new Error("API Check Failed");

        let data = await response.json();
        fillTable(data.outages);
        
        checkMyAreaBtn.style.display = "none";
        resetBtn.style.display = "inline-block";
        statusBar.textContent = `Found ${data.outages.length} nearby outages.`;
        statusBar.style.color = "var(--success-green)";

    } catch(e) {
        console.error("Check outages error", e);
        statusBar.textContent = "Error: Could not check proximity to outages.";
        statusBar.style.color = "var(--danger-red)";
    }
}

/**
 * Requests GPS coordinates and triggers proximity check
 */
async function getCoords() {
    statusBar.textContent = "Waiting for location permission..."; 
    
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const lat = position.coords.latitude;
                const lon = position.coords.longitude;
                check_outages(lat, lon);
            },
            (error) => {
                const msg = (error.code === error.PERMISSION_DENIED) 
                    ? ' Error: Location access denied.' 
                    : ` Error getting location: ${error.message}`;
                statusBar.textContent = msg;
                statusBar.style.color = "var(--danger-red)";
            }
        );
    } else {
        statusBar.textContent = 'Geolocation is not supported by this browser.';
    }
}

/**
 * Fetches all outages from the backend
 */
async function getOutagesData() {
    if (outagesData && outagesData.length > 0) {
        fillTable(outagesData);
        return outagesData;
    }
    
    statusBar.textContent = "Fetching latest outages...";
    try {
        const response = await fetch("/api/outages");

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `Server error: ${response.status}`);
        }

        const data = await response.json();
        if (!Array.isArray(data)) throw new Error("Invalid data format.");

        outagesData = data;
        fillTable(outagesData);
        
        statusBar.textContent = "Data updated successfully."; 
        statusBar.style.color = "var(--success-green)";
        return data;

    } catch(e) {
        console.error("Get outages data error: ", e);
        statusBar.textContent = `ERROR: ${e.message}`;
        statusBar.style.color = "var(--danger-red)";
        return null;
    }
}

/**
 * Initialize UI Elements and Event Listeners
 */
document.addEventListener('DOMContentLoaded', function() {
    // User Menu Dropdown Toggle
    const menuButton = document.getElementById('userMenuBtn');
    const menuDropdown = document.getElementById('userMenuDropdown');

    if (menuButton && menuDropdown) {
        menuButton.addEventListener('click', function(e) {
            e.stopPropagation();
            menuDropdown.classList.toggle('show');
        });

        window.addEventListener('click', function() {
            if (menuDropdown.classList.contains('show')) {
                menuDropdown.classList.remove('show');
            }
        });
    }

    // Initial Load
    getOutagesData();
});

// Search Input Listener
if (searchInput) {
    searchInput.addEventListener('input', function() {
        getFilteredOutages(searchInput.value);
    });
}

// Proximity Button Listener
if (checkMyAreaBtn) {
    checkMyAreaBtn.addEventListener("click", () => {
        if (searchInput) searchInput.value = ''; 
        getCoords();
    });
}

// Reset Button Listener
if (resetBtn) {
    resetBtn.addEventListener("click", () => {
        fillTable(outagesData); 
        if (searchInput) searchInput.value = '';
        checkMyAreaBtn.style.display = "inline-block";
        resetBtn.style.display = "none";
        statusBar.textContent = "Showing all scheduled outages.";
        statusBar.style.color = "var(--text-main)";
    });
}