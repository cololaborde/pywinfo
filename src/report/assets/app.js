const DATA = __HWINFO_DATA__;


// ============================================================
// HELPERS
// ============================================================

function escapeHtml(value) {

    if (value === null ||
        value === undefined) {
        return "";
    }

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function displayValue(value, fallback = "—") {

    if (value === null ||
        value === undefined ||
        value === "") {
        return fallback;
    }

    return escapeHtml(value);
}


function deviceHtml(device) {

    const stateBadge = device.state
        ? `<span class="badge ${device.state === "UP" ? "badge-up" : "badge-down"}">${escapeHtml(device.state)}</span>`
        : "";

    const ipBadges = (device.ip_addresses && device.ip_addresses.length)
        ? `
            <div class="device-meta" style="margin-top:6px;">
                ${device.ip_addresses.map(ip => `
                    <span class="badge">
                        ${escapeHtml(ip.address)}${ip.prefix ? "/" + escapeHtml(ip.prefix) : ""}
                    </span>
                `).join("")}
            </div>
        `
        : "";

    return `
        <div class="device">

            <div class="device-name">
                ${displayValue(device.model, "Dispositivo")}
                ${stateBadge}
            </div>

            <div class="device-meta">

                ${device.vendor
                    ? `<span>Vendor: ${escapeHtml(device.vendor)}</span>`
                    : ""}

                ${device.driver
                    ? `<span>Driver: ${escapeHtml(device.driver)}</span>`
                    : ""}

                ${device.interface
                    ? `<span>Interface: ${escapeHtml(device.interface)}</span>`
                    : ""}

                ${device.mac
                    ? `<span>MAC: ${escapeHtml(device.mac)}</span>`
                    : ""}

                ${device.mtu
                    ? `<span>MTU: ${escapeHtml(device.mtu)}</span>`
                    : ""}

                ${device.bus_id
                    ? `<span>Bus: ${escapeHtml(device.bus_id)}</span>`
                    : ""}

                ${device.device
                    ? `<span>Device: ${escapeHtml(device.device)}</span>`
                    : ""}

                ${device.size
                    ? `<span>Size: ${escapeHtml(device.size)}</span>`
                    : ""}

            </div>

            ${ipBadges}

        </div>
    `;
}


function renderDevices(containerId, devices) {

    const container =
        document.getElementById(containerId);

    if (!devices || devices.length === 0) {

        container.innerHTML = `
            <div class="card-small">
                No se detectaron dispositivos.
            </div>
        `;

        return;
    }

    container.innerHTML =
        devices.map(deviceHtml).join("");
}


// ============================================================
// NAVIGATION
// ============================================================

function showPage(pageId, button) {

    document
        .querySelectorAll(".page")
        .forEach(page => {
            page.classList.remove("active");
        });

    document
        .querySelectorAll(".nav button")
        .forEach(btn => {
            btn.classList.remove("active");
        });

    document
        .getElementById(pageId)
        .classList.add("active");

    button.classList.add("active");
}


// ============================================================
// OVERVIEW
// ============================================================

function renderOverview() {

    const cpu = DATA.cpu || {};
    const memory = DATA.memory || {};
    const gpu = DATA.gpu || [];
    const disks = DATA.disks || [];
    const network = DATA.network || [];

    const cards = [

        {
            title: "CPU",
            value: cpu.model || "No detectado",
            small:
                cpu.physical_cores && cpu.logical_processors
                    ? `${cpu.physical_cores} núcleos · ${cpu.logical_processors} hilos`
                    : cpu.logical_processors
                        ? `${cpu.logical_processors} CPUs lógicas`
                        : ""
        },

        {
            title: "Memory",
            value:
                memory.total_gb
                    ? `${memory.total_gb} GB`
                    : "No detectada",
            small:
                memory.modules && memory.modules.length
                    ? `${memory.modules.length} módulo(s) físico(s)`
                    : "RAM total"
        },

        {
            title: "GPU",
            value:
                gpu.length
                    ? gpu[0].model
                    : "No detectada",
            small:
                gpu.length > 1
                    ? `${gpu.length} GPUs detectadas`
                    : ""
        },

        {
            title: "Storage",
            value:
                disks.length
                    ? `${disks.length} disco(s)`
                    : "No detectado",
            small:
                disks.map(d => d.size_human)
                    .filter(Boolean)
                    .join(" · ")
        },

        {
            title: "Network",
            value:
                network.length
                    ? `${network.length} interfaces`
                    : "No detectada",
            small:
                network.filter(n => n.state === "UP").length
                    ? `${network.filter(n => n.state === "UP").length} activa(s)`
                    : network
                        .map(n => n.interface)
                        .filter(Boolean)
                        .join(" · ")
        },

        {
            title: "Monitor",
            value:
                DATA.monitors?.length
                    ? DATA.monitors[0].model
                    : "No detectado",
            small:
                DATA.monitors?.length > 1
                    ? `${DATA.monitors.length} monitores`
                    : ""
        },

    ];


    document.getElementById("overviewCards").innerHTML =
        cards.map(card => `
            <div class="card">

                <div class="card-title">
                    ${escapeHtml(card.title)}
                </div>

                <div class="card-value">
                    ${escapeHtml(card.value)}
                </div>

                <div class="card-small">
                    ${escapeHtml(card.small || "")}
                </div>

            </div>
        `).join("");
}


// ============================================================
// CPU
// ============================================================

function renderCPU() {

    const cpu = DATA.cpu || {};
    const cache = cpu.cache || {};

    const freqLabel = (mhz) =>
        mhz ? (mhz / 1000).toFixed(2) + " GHz" : "—";

    document.getElementById("cpuContent").innerHTML = `

        <div class="grid">

            <div class="card">
                <div class="card-title">Model</div>
                <div class="card-value">${displayValue(cpu.model)}</div>
                <div class="card-small">${displayValue(cpu.architecture, "")}</div>
            </div>

            <div class="card">
                <div class="card-title">Vendor</div>
                <div class="card-value">${displayValue(cpu.vendor)}</div>
            </div>

            <div class="card">
                <div class="card-title">Topología</div>
                <div class="card-value">
                    ${cpu.physical_cores ? cpu.physical_cores + " núcleos" : "—"}
                    ${cpu.logical_processors ? " / " + cpu.logical_processors + " hilos" : ""}
                </div>
                <div class="card-small">
                    ${cpu.sockets ? cpu.sockets + " socket(s)" : ""}
                    ${cpu.threads_per_core ? ` · ${cpu.threads_per_core} hilos/núcleo` : ""}
                </div>
            </div>

            <div class="card">
                <div class="card-title">Frecuencia</div>
                <div class="card-value">
                    ${cpu.max_mhz ? freqLabel(cpu.max_mhz) + " máx" : "—"}
                </div>
                <div class="card-small">
                    ${cpu.min_mhz ? "mín " + freqLabel(cpu.min_mhz) : ""}
                </div>
            </div>

            <div class="card">
                <div class="card-title">Cache</div>
                <div class="card-value" style="font-size: 15px;">
                    L1d ${displayValue(cache.l1d)} · L1i ${displayValue(cache.l1i)}
                </div>
                <div class="card-small">
                    L2 ${displayValue(cache.l2)} · L3 ${displayValue(cache.l3)}
                </div>
            </div>

            <div class="card">
                <div class="card-title">Virtualización</div>
                <div class="card-value">${displayValue(cpu.virtualization)}</div>
            </div>

        </div>


        <div class="section">

            <h2>Frecuencia actual por núcleo lógico</h2>

            <div class="chart-container">

                <canvas id="cpuChart"></canvas>

            </div>

        </div>
    `;


    const frequencies =
        cpu.frequencies || [];

    // Con lscpu/proc_cpuinfo las frecuencias ya llegan como números
    // (MHz reales, leídos en el momento). Solo en el último fallback
    // de hwinfo pueden llegar como texto tipo "2400MHz".
    const values = frequencies
        .map(value => {

            if (typeof value === "number") {
                return value;
            }

            const match =
                String(value)
                    .match(/([\d.]+)\s*MHz/i);

            return match
                ? parseFloat(match[1])
                : null;

        })
        .filter(value => value !== null);


    if (!values.length) {
        return;
    }


    new Chart(
        document.getElementById("cpuChart"),
        {
            type: "bar",

            data: {

                labels:
                    values.map(
                        (_, index) =>
                            `CPU ${index + 1}`
                    ),

                datasets: [
                    {
                        label: "MHz",
                        data: values,
                    }
                ]

            },

            options: {

                responsive: true,

                maintainAspectRatio: false,

                plugins: {
                    legend: {
                        display: false
                    }
                }

            }
        }
    );
}


// ============================================================
// GPU
// ============================================================

function renderGPU() {

    renderDevices(
        "gpuContent",
        DATA.gpu || []
    );
}


// ============================================================
// MEMORY
// ============================================================

function renderMemory() {

    const memory =
        DATA.memory || {};

    const modules =
        memory.modules || [];

    const modulesHtml = modules.length
        ? `
            <div class="section">

                <h2>Módulos instalados</h2>

                <table>

                    <thead>
                        <tr>
                            <th>Slot</th>
                            <th>Tamaño</th>
                            <th>Tipo</th>
                            <th>Velocidad</th>
                            <th>Fabricante</th>
                            <th>Part number</th>
                        </tr>
                    </thead>

                    <tbody>

                        ${modules.map(m => `
                            <tr>
                                <td>${displayValue(m.locator)}</td>
                                <td>${displayValue(m.size)}</td>
                                <td>${displayValue(m.type)}</td>
                                <td>${displayValue(m.configured_speed || m.speed)}</td>
                                <td>${displayValue(m.manufacturer)}</td>
                                <td>${displayValue(m.part_number)}</td>
                            </tr>
                        `).join("")}

                    </tbody>

                </table>

            </div>
        `
        : `
            <div class="card-small">
                No se pudo leer el detalle por módulo (requiere
                dmidecode con permisos de root). Se muestra solo el
                total del sistema.
            </div>
        `;

    document.getElementById(
        "memoryContent"
    ).innerHTML = `

        <div class="grid">

            <div class="card">

                <div class="card-title">
                    Total RAM
                </div>

                <div class="card-value">
                    ${
                        memory.total_gb
                            ? memory.total_gb + " GB"
                            : "—"
                    }
                </div>

                <div class="card-small">
                    ${
                        modules.length
                            ? modules.length + " módulo(s) físico(s)"
                            : ""
                    }
                </div>

            </div>

        </div>

        ${modulesHtml}

    `;
}


// ============================================================
// STORAGE
// ============================================================
//
// Cada disco viene de lsblk con su tamaño exacto en bytes (no de
// hwinfo), su tipo real (HDD/SSD/NVMe/Desconocido) y la lista de
// particiones con su propio tamaño/filesystem/mountpoint.

function partitionsTableHtml(partitions) {

    if (!partitions || !partitions.length) {
        return `
            <div class="card-small">
                No se detectaron particiones (o el disco no tiene
                tabla de particiones).
            </div>
        `;
    }

    return `
        <table>

            <thead>
                <tr>
                    <th>Partición</th>
                    <th>Tamaño</th>
                    <th>Filesystem</th>
                    <th>Mountpoint</th>
                </tr>
            </thead>

            <tbody>

                ${partitions.map(p => `
                    <tr>
                        <td>${displayValue(p.device)}</td>
                        <td>${displayValue(p.size_human)}</td>
                        <td>${displayValue(p.filesystem)}</td>
                        <td>${displayValue(p.mountpoint)}</td>
                    </tr>
                `).join("")}

            </tbody>

        </table>
    `;
}


function diskCardHtml(disk) {

    return `
        <div class="section">

            <h2>
                ${displayValue(disk.device)} — ${displayValue(disk.model)}
                ${disk.type
                    ? `<span class="badge">${escapeHtml(disk.type)}</span>`
                    : ""}
                ${disk.removable
                    ? `<span class="badge">Extraíble</span>`
                    : ""}
            </h2>

            <div class="device-meta" style="margin-bottom:14px;">

                ${disk.vendor
                    ? `<span>Vendor: ${escapeHtml(disk.vendor)}</span>`
                    : ""}

                ${disk.serial
                    ? `<span>Serial: ${escapeHtml(disk.serial)}</span>`
                    : ""}

                ${disk.transport
                    ? `<span>Interfaz: ${escapeHtml(disk.transport.toUpperCase())}</span>`
                    : ""}

                ${disk.size_human
                    ? `<span>Tamaño: ${escapeHtml(disk.size_human)}</span>`
                    : `<span>Tamaño: no disponible</span>`}

                ${disk.partition_table
                    ? `<span>Tabla: ${escapeHtml(disk.partition_table.toUpperCase())}</span>`
                    : ""}

                ${(!disk.partitions || !disk.partitions.length) && disk.filesystem
                    ? `<span>Filesystem: ${escapeHtml(disk.filesystem)}</span>`
                    : ""}

                ${(!disk.partitions || !disk.partitions.length) && disk.mountpoint
                    ? `<span>Mountpoint: ${escapeHtml(disk.mountpoint)}</span>`
                    : ""}

            </div>

            ${partitionsTableHtml(disk.partitions)}

        </div>
    `;
}


function renderStorage() {

    const disks =
        DATA.disks || [];

    const container =
        document.getElementById("storageContent");

    if (!disks.length) {

        container.innerHTML = `
            <div class="card">
                No se detectaron discos.
            </div>
        `;

        return;
    }

    container.innerHTML =
        disks.map(diskCardHtml).join("");
}


// ============================================================
// NETWORK
// ============================================================

function renderNetwork() {

    renderDevices(
        "networkContent",
        DATA.network || []
    );
}


// ============================================================
// DEVICES
// ============================================================

function renderDevicesPage() {

    const container =
        document.getElementById(
            "devicesContent"
        );

    const sections = [

        ["USB", DATA.usb || []],

        ["Audio", DATA.audio || []],

        ["Bluetooth", DATA.bluetooth || []],

        ["Cameras", DATA.cameras || []],

        ["Monitors", DATA.monitors || []],

    ];


    container.innerHTML =
        sections.map(
            ([title, devices]) => `

                <div class="section">

                    <h2>
                        ${escapeHtml(title)}
                    </h2>

                    ${
                        devices.length
                            ? devices.map(deviceHtml).join("")
                            : `<div class="card-small">
                                No detectado.
                               </div>`
                    }

                </div>

            `
        ).join("");
}


// ============================================================
// STORAGE CHART
// ============================================================
//
// Usa directamente disk.size_gb (calculado en Python a partir de
// bytes exactos de lsblk). Ya no se parsean strings como "500G".

function renderStorageChart() {

    const disks =
        DATA.disks || [];

    if (!disks.length) {
        return;
    }

    const labels =
        disks.map(
            disk =>
                disk.model ||
                disk.device ||
                "Disco"
        );

    const sizes =
        disks.map(
            disk => disk.size_gb || 0
        );

    new Chart(
        document.getElementById(
            "storageChart"
        ),
        {
            type: "bar",

            data: {

                labels,

                datasets: [
                    {
                        label: "GB",
                        data: sizes
                    }
                ]

            },

            options: {

                responsive: true,

                maintainAspectRatio: false,

                plugins: {
                    legend: {
                        display: false
                    }
                }

            }
        }
    );
}


// ============================================================
// RAW
// ============================================================

function renderRaw() {

    const blocks =
        DATA.raw_blocks || [];

    document.getElementById(
        "rawContent"
    ).innerHTML =
        blocks.map(
            block => {

                const properties =
                    block.properties || {};

                return `

                    <details>

                        <summary>
                            ${escapeHtml(
                                block.id +
                                ": " +
                                block.header
                            )}
                        </summary>

                        <pre>${escapeHtml(
                            JSON.stringify(
                                properties,
                                null,
                                2
                            )
                        )}</pre>

                    </details>

                `;

            }
        ).join("");
}


// ============================================================
// INIT
// ============================================================

renderOverview();
renderCPU();
renderGPU();
renderMemory();
renderStorage();
renderNetwork();
renderDevicesPage();
renderStorageChart();
renderRaw();
