
const outagesTableBody = document.querySelector('#outagesTable tbody');
const resetBtn = document.getElementById("resetBtn"); 
const checkMyAreaBtn = document.getElementById("checkMyAreaBtn"); 
const statusBar = document.getElementById("localStatusMessage");
const emptyMessage = document.getElementById("emptyMessage");
const searchInput = document.getElementById('outageSearch'); 

let userLat;
let userLon;
let outagesData;
const R = 6371; 

function highlightMatch(text, filter) {
    if (!filter) return text;

    const escapedFilter = filter.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedFilter})`, 'gi');
    
    return text.replace(regex, '<span class="highlight">$1</span>');
}

function fillTable(outagesToDisplay, currentFilter = '') {
    outagesTableBody.innerHTML = '';
    
    emptyMessage.style.display = 'none';
    const  filterText =  currentFilter.trim();

    outagesToDisplay.sort((a, b) => {
        return -(new Date(a.date) - new Date(b.date));
    });

    if (outagesToDisplay.length == 0) {return;
    }

     const shouldExpand = filterText.length > 0;

    outagesToDisplay.forEach(outage => {
        const row = outagesTableBody.insertRow();
        
        let distanceCell = '';
        if (outage.distance_km) {
            distanceCell = ` <strong>(${outage.distance_km} km)</strong>`;
            row.style.backgroundColor = '#fff3cd'; // Highlight nearby outages
        }

        // --- Date Logic (Kept As Is) ---
        const dateNow = new Date();
        const outageDate = new Date(`${outage.date}T${outage.time}`);
        dateNow.setHours(0,0,0,0);
        outageDate.setHours(0,0,0,0);
        
        if (dateNow.getDate() <= outageDate.getDate()){
             row.style.backgroundColor = "#ff7300a9";
        }
   
        const highlightedArea = highlightMatch(outage.area, filterText);
        row.insertCell().innerHTML = highlightedArea + distanceCell; 
        row.insertCell().textContent = outage.date;
        row.insertCell().textContent = outage.time;
        const subAreasText = Array.isArray(outage.sub_areas) ? outage.sub_areas.join(', ') : outage.sub_areas;
        const highlightedSubAreas = highlightMatch(subAreasText, filterText);
    
        const detailsOpenAttribute =  shouldExpand ?   'open' : '';

        row.insertCell().innerHTML = `<details name="sub_areas" ${detailsOpenAttribute}>
            <summary>Sub Areas</summary>
            <p>${highlightedSubAreas}</p>   
        </details>`;
    }) ;
}

function getFilteredOutages(filterText) {
    const filter = filterText.trim().toUpperCase();

    if (!filter) {
        fillTable(outagesData, filterText); 
        return;
    }

    const filteredData = outagesData.filter(outage => {
        const areaMatch = outage.area.toUpperCase().includes(filter);
        
        const subAreaMatch = Array.isArray(outage.sub_areas) && outage.sub_areas.some(subArea => 
            subArea.toUpperCase().includes(filter)
        );

        return areaMatch || subAreaMatch;
    });

    fillTable(filteredData, filterText);
}

function haversine_distance(lat1, lon1, lat2, lon2) {
    const dLat = (lat2 - lat1) * (Math.PI / 180);
    const dLon = (lon2 - lon1) * (Math.PI / 180);

    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(lat1 * (Math.PI / 180)) * Math.cos(lat2 * (Math.PI / 180)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);

    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

async function check_outages(lat,lon){
    try{
        let response = await fetch ( `http://127.0.0.1:5000/api/check_outage?lat=${lat}&lon=${lon}` );
        let data = await response.json();
        
        fillTable(data.outages) 
        
        checkMyAreaBtn.style.display ="none";
        resetBtn.style.display = "block";

        if (!response.ok){
            console.log("big flop");
            throw new Error();
        }  
    }catch(e){
        console.error("Check outages error",e);
        statusBar.textContent = "Error: Could not check proximity to outages.";
    }
}

async function getCoords(){
    statusBar.textContent = "Waiting for location permission..."; 
    
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const a = position.coords.latitude;
                const b = position.coords.longitude;
                check_outages(a,b);
                statusBar.textContent = "";
            },
            (error) => {
                const msg = (error.code === error.PERMISSION_DENIED) ? ' Error: Location access denied. Cannot filter table without location.': ` Error getting location: ${error.message}`;
                statusBar.textContent = msg;
            }
        );
    } else {
        statusBar.textContent = 'Geolocation is not supported by this browser.';
    }
}

async function getOutagesData(){
    if (outagesData && outagesData.length > 0) {
        fillTable(outagesData);
        return outagesData;
    }
    
    let data;
    try{
        const response = await fetch("http://127.0.0.1:5000/api/outages");
        statusBar.textContent = "Fetching outages data";

        if (!response.ok){
            statusBar.textContent = "ERROR: Failed to fetch outages data";
            throw new Error ("Failed to fetch outages Data : ");
        }

        data = await response.json();
        
        outagesData = data;
        fillTable(outagesData);
        
        statusBar.textContent = ""; 
        return data;

    }
    catch(e){
        console.error("Get outages data error: ",e );
        statusBar.textContent = "ERROR: Failed to fetch scheduled outages.";
        return null;
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const menuButton = document.getElementById('userMenuBtn');
    const menuDropdown = document.getElementById('userMenuDropdown');

    if (menuButton && menuDropdown) {
        menuButton.addEventListener('click', function() {
            menuDropdown.classList.toggle('show');
        });

        window.addEventListener('click', function(event) {
            if (!event.target.matches('#userMenuBtn')) {
                if (menuDropdown.classList.contains('show')) {
                    menuDropdown.classList.remove('show');
                }
            }
        });
    }
});


getOutagesData();

if (searchInput) {
    searchInput.addEventListener('keyup', function() {
        getFilteredOutages(searchInput.value);
    });
}

if (checkMyAreaBtn) {
    checkMyAreaBtn.addEventListener("click",()=>{
        if (searchInput) searchInput.value = ''; 
        getCoords();
    });
}

if (resetBtn) {
        resetBtn.addEventListener("click",()=>{
            fillTable(outagesData); 

            if (searchInput) searchInput.value = '';

            checkMyAreaBtn.style.display ="block";
            resetBtn.style.display = "none";
            statusBar.textContent = "";
        });
    }


