import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';

const viewport = document.getElementById('viewport');
const statsLine = document.getElementById('stats-line');
const cmdInput = document.getElementById('cmd-input');
const cmdResults = document.getElementById('cmd-results');
const zoneListEl = document.getElementById('zone-list');
const inspector = document.getElementById('inspector');
const inspRoom = document.getElementById('insp-room');
const inspPrivacy = document.getElementById('insp-privacy');
const inspTitle = document.getElementById('insp-title');
const inspUri = document.getElementById('insp-uri');
const inspSpecial = document.getElementById('insp-special');
const atomsList = document.getElementById('atoms-list');
const bitsList = document.getElementById('bits-list');
const atomsCount = document.getElementById('atoms-count');
const bitsCount = document.getElementById('bits-count');
const inspNotes = document.getElementById('insp-notes');
const shelfPhotoWrap = document.getElementById('shelf-photo-wrap');
const shelfPhotoImg = document.getElementById('shelf-photo-img');
const inputMountFolder = document.getElementById('input-mount-folder');
const fsList = document.getElementById('fs-list');
const devList = document.getElementById('dev-list');
const devCount = document.getElementById('dev-count');
const agentDrawer = document.getElementById('agent-drawer');
const agentContext = document.getElementById('agent-context');
const agentLog = document.getElementById('agent-log');
const agentInput = document.getElementById('agent-input');
const mediaModal = document.getElementById('media-modal');
const mediaTitle = document.getElementById('media-title');
const mediaContent = document.getElementById('media-content');
const toastEl = document.getElementById('toast');

// ---------------------------------------------------------------------------
// Three.js Scene, Lighting Moods & Smooth Orbit Controls
// ---------------------------------------------------------------------------
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x9ec5e8);
scene.fog = new THREE.Fog(0xb6d4ee, 22, 54);

const camera = new THREE.PerspectiveCamera(58, window.innerWidth / window.innerHeight, 0.08, 120);
camera.position.set(2.4, 8.8, 3.8);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.12;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
viewport.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.target.set(-0.6, 0.8, -0.5);
controls.maxPolarAngle = Math.PI * 0.49;
controls.minDistance = 0.8;
controls.maxDistance = 26;

const hemi = new THREE.HemisphereLight(0xdceeff, 0x7b634b, 0.95);
scene.add(hemi);

const sun = new THREE.DirectionalLight(0xfff1d6, 2.3);
sun.position.set(-10, 12, -9);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
scene.add(sun);

const interiorLights = [
  [-1.0, 2.6, -5.0, 0xfff4e0, 1.2],
  [-2.0, 2.55, 0.3, 0xffedd2, 1.0],
  [-2.1, 2.55, 4.0, 0xf2f6ff, 1.2],
  [2.0, 2.55, 3.0, 0xffeed6, 0.95],
].map(([x, y, z, col, inten]) => {
  const pl = new THREE.PointLight(col, inten, 9, 1.6);
  pl.position.set(x, y, z);
  scene.add(pl);
  return pl;
});

function applyMood(mood) {
  document.querySelectorAll('.mood-btn').forEach((b) => b.classList.toggle('active', b.dataset.mood === mood));
  if (mood === 'afternoon') {
    scene.background.setHex(0x9ec5e8);
    scene.fog.color.setHex(0xb6d4ee);
    sun.color.setHex(0xfff1d6); sun.intensity = 2.3;
    hemi.intensity = 0.95;
    interiorLights.forEach((l) => { l.color.setHex(0xfff4e0); l.intensity = 1.1; });
  } else if (mood === 'studio') {
    scene.background.setHex(0x1b2638);
    scene.fog.color.setHex(0x1b2638);
    sun.color.setHex(0xd6ecff); sun.intensity = 1.2;
    hemi.intensity = 0.85;
    interiorLights.forEach((l, i) => { l.color.setHex(i === 2 ? 0xd0f4ff : 0xeef6ff); l.intensity = i === 2 ? 2.4 : 1.3; });
  } else if (mood === 'lounge') {
    scene.background.setHex(0x090d18);
    scene.fog.color.setHex(0x090d18);
    sun.color.setHex(0x465b9e); sun.intensity = 0.45;
    hemi.intensity = 0.38;
    interiorLights.forEach((l, i) => { l.color.setHex(i === 0 ? 0xffaa66 : 0xb478ff); l.intensity = 1.65; });
  }
}

// ---------------------------------------------------------------------------
// Load Apartment GLB + Live Custom Wall Art Texture Swap + COLMAP Overlay
// ---------------------------------------------------------------------------
let ceilingMesh = null;
let wallArtMesh = null;
let printerHeadMesh = null;
let printerSweepUntil = 0;
const texLoader = new THREE.TextureLoader();

function applyWallArtTexture(relPath) {
  if (!wallArtMesh || !relPath) return;
  texLoader.load(`../${relPath}?t=${Date.now()}`, (tex) => {
    tex.colorSpace = THREE.SRGBColorSpace;
    wallArtMesh.material = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.5 });
  });
}

new GLTFLoader().load('../exports/apartment_escape_room.glb', (gltf) => {
  const root = gltf.scene;
  root.traverse((c) => {
    if (c.isMesh) {
      c.castShadow = !c.name.includes('Skyline') && !c.name.includes('Glass');
      c.receiveShadow = true;
      if (c.name.includes('Glass')) {
        c.material.transparent = true;
        c.material.opacity = 0.14;
        c.material.depthWrite = false;
      }
      if (c.name === 'Ceiling_Main') { ceilingMesh = c; c.visible = false; }
      if (c.name === 'Off_3DPrinter1_Head') printerHeadMesh = c;
      if (c.name === 'Din_WallArt_CanvasTop') {
        wallArtMesh = c;
        if (homeGraph.custom_wall_art) applyWallArtTexture(homeGraph.custom_wall_art);
      }
    }
  });
  scene.add(root);
});

let scanCloud = null;
let scanVisible = false;
fetch('../scan/living_scan_threejs.json')
  .then((r) => r.json())
  .then((data) => {
    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.Float32BufferAttribute(data.positions, 3));
    geom.setAttribute('color', new THREE.Float32BufferAttribute(data.colors, 3));
    scanCloud = new THREE.Points(geom, new THREE.PointsMaterial({ size: 0.055, vertexColors: true, transparent: true, opacity: 0.88 }));
    scanCloud.visible = false;
    scene.add(scanCloud);
  })
  .catch(() => {});

// ---------------------------------------------------------------------------
// Home Graph State, 3D Spatial Pins & Highlight Beacon
// ---------------------------------------------------------------------------
let homeGraph = { nodes: [] };
let selectedNodeId = null;
let currentFsFolder = '';
let currentFsParent = '';
let guestMode = new URLSearchParams(window.location.search).get('guest') === '1';

const pinGroup = new THREE.Group();
scene.add(pinGroup);
const pinMeshes = [];

const highlightGroup = new THREE.Group();
highlightGroup.visible = false;
const ringMesh = new THREE.Mesh(
  new THREE.RingGeometry(0.18, 0.28, 32),
  new THREE.MeshBasicMaterial({ color: 0x00f0ff, side: THREE.DoubleSide, transparent: true, opacity: 0.9 })
);
ringMesh.rotation.x = -Math.PI / 2;
const beamMesh = new THREE.Mesh(
  new THREE.CylinderGeometry(0.03, 0.12, 2.2, 16, 1, true),
  new THREE.MeshBasicMaterial({ color: 0x00e5ff, transparent: true, opacity: 0.24, side: THREE.DoubleSide })
);
beamMesh.position.y = 1.1;
highlightGroup.add(ringMesh, beamMesh);
scene.add(highlightGroup);

let flyAnim = null;
function flyCameraTo(pos, look, durMs = 780) {
  flyAnim = {
    startPos: camera.position.clone(),
    endPos: new THREE.Vector3(...pos),
    startLook: controls.target.clone(),
    endLook: new THREE.Vector3(...look),
    t0: performance.now(),
    dur: durMs,
  };
}

function showToast(msg, ms = 3200) {
  toastEl.textContent = msg;
  toastEl.classList.remove('hidden');
  clearTimeout(toastEl._t);
  toastEl._t = setTimeout(() => toastEl.classList.add('hidden'), ms);
}

async function apiPost(url, payload) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return res.json();
}

function buildPins() {
  while (pinGroup.children.length) pinGroup.remove(pinGroup.children[0]);
  pinMeshes.length = 0;

  for (const node of homeGraph.nodes) {
    if (guestMode && node.privacy === 'private') continue;
    const col = new THREE.Color(node.color || '#58d5ff');
    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(0.11, 18, 18),
      new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.85, roughness: 0.2 })
    );
    sphere.position.set(...node.position_threejs);
    sphere.userData = { nodeId: node.id, baseY: node.position_threejs[1] };

    const halo = new THREE.Mesh(
      new THREE.RingGeometry(0.14, 0.18, 24),
      new THREE.MeshBasicMaterial({ color: col, side: THREE.DoubleSide, transparent: true, opacity: 0.55 })
    );
    halo.rotation.x = -Math.PI / 2;
    sphere.add(halo);
    pinGroup.add(sphere);
    pinMeshes.push(sphere);
  }
}

function renderSidebar() {
  const byRoom = new Map();
  let totalAtoms = 0;
  let totalBits = 0;
  for (const n of homeGraph.nodes) {
    totalAtoms += (n.physical_items || []).reduce((s, i) => s + (i.qty || 1), 0);
    totalBits += (n.digital_files || []).length;
    if (!byRoom.has(n.room)) byRoom.set(n.room, []);
    byRoom.get(n.room).push(n);
  }
  statsLine.textContent = `${homeGraph.nodes.length} Spatial Nodes · ${totalAtoms} Physical Parts · ${totalBits} Digital Files`;

  zoneListEl.innerHTML = '';
  for (const [room, nodes] of byRoom.entries()) {
    const hdr = document.createElement('div');
    hdr.className = 'room-group';
    hdr.textContent = room;
    zoneListEl.appendChild(hdr);

    for (const n of nodes) {
      const lockedForGuest = guestMode && n.privacy === 'private';
      const btn = document.createElement('button');
      btn.className = `zone-btn ${n.id === selectedNodeId ? 'selected' : ''} ${lockedForGuest ? 'locked' : ''}`;
      const aCnt = (n.physical_items || []).length;
      const bCnt = (n.digital_files || []).length;
      btn.innerHTML = `
        <span class="zone-dot" style="background:${n.color || '#58d5ff'}"></span>
        <span class="zone-name">${lockedForGuest ? '🔒 ' : ''}${n.label}</span>
        <span class="zone-meta">${lockedForGuest ? 'Private' : `${aCnt}A · ${bCnt}B`}</span>
      `;
      btn.addEventListener('click', () => {
        if (lockedForGuest) {
          showToast(`Private zone (${n.room}) — locked in Guest View!`);
          return;
        }
        selectNode(n.id, true);
      });
      zoneListEl.appendChild(btn);
    }
  }
}

function openMediaLightbox(title, html) {
  mediaTitle.textContent = title;
  mediaContent.innerHTML = html;
  mediaModal.classList.remove('hidden');
}

document.getElementById('media-close').addEventListener('click', () => {
  mediaModal.classList.add('hidden');
  mediaContent.innerHTML = '';
});

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = reject;
    fr.readAsDataURL(file);
  });
}

function renderSpecialPanel(node) {
  inspSpecial.innerHTML = '';
  inspSpecial.classList.add('hidden');

  if (node.category === 'tv') {
    inspSpecial.classList.remove('hidden');
    inspSpecial.innerHTML = `
      <div class="special-title">LIVING ROOM TV — LIVE MEDIA &amp; CO-WATCH DECK</div>
      <div class="special-row">
        <button class="mini-btn accent" id="tv-lofi">▶ YouTube Lo-Fi Live</button>
        <button class="mini-btn" id="tv-custom">Embed YouTube URL</button>
        <button class="mini-btn" id="tv-share">📡 Share to Room TV</button>
      </div>
    `;
    const launchTV = (title, embed, broadcast = false) => {
      openMediaLightbox(title, `<iframe src="${embed}?autoplay=1" allow="autoplay; encrypted-media" allowfullscreen></iframe>`);
      if (broadcast) {
        apiPost('/api/tv/sync', { title, embed_url: embed, shared_by: myDisplayName }).then(() => showToast('Shared video to Living Room TV for all connected guests!'));
      }
    };
    inspSpecial.querySelector('#tv-lofi').addEventListener('click', () => launchTV('Living Room TV — Lofi Girl Radio', 'https://www.youtube.com/embed/jfKfPfyJRdk', false));
    inspSpecial.querySelector('#tv-custom').addEventListener('click', () => {
      const url = prompt('Paste a YouTube video URL (e.g. https://www.youtube.com/watch?v=...)');
      if (!url) return;
      const m = url.match(/(?:v=|youtu\.be\/|embed\/)([A-Za-z0-9_-]{11})/);
      launchTV('Living Room TV', m ? `https://www.youtube.com/embed/${m[1]}` : url, false);
    });
    inspSpecial.querySelector('#tv-share').addEventListener('click', () => {
      const url = prompt('Share YouTube URL to everyone in the Living Room (leave blank for Lo-Fi Radio):') || 'https://www.youtube.com/embed/jfKfPfyJRdk';
      const m = url.match(/(?:v=|youtu\.be\/|embed\/)([A-Za-z0-9_-]{11})/);
      launchTV('Shared Living Room Co-Watch', m ? `https://www.youtube.com/embed/${m[1]}` : url, true);
    });
  } else if (node.category === 'favorites') {
    inspSpecial.classList.remove('hidden');
    inspSpecial.innerHTML = `
      <div class="special-title">DINING WALL FRAME — LIVE 3D ART SWAP</div>
      <div class="special-row">
        <label class="mini-btn accent" style="cursor:pointer;text-align:center;">
          🖼 Hang Custom Image on 3D Wall
          <input id="input-wall-art" type="file" accept="image/*" style="display:none;" />
        </label>
      </div>
    `;
    inspSpecial.querySelector('#input-wall-art').addEventListener('change', async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const dataUrl = await readFileAsDataUrl(file);
      const res = await apiPost('/api/wall-art', { data_url: dataUrl });
      if (res.ok) {
        homeGraph = res.graph;
        applyWallArtTexture(res.path);
        showToast('Hung new custom art directly onto your 3D Dining Wall!');
      }
    });
  } else if (node.category === 'stereo') {
    inspSpecial.classList.remove('hidden');
    inspSpecial.innerHTML = `
      <div class="special-title">MUSIC NOOK STEREO — PERSISTENT ROOM AUDIO</div>
      <div class="special-row">
        <button class="mini-btn accent" id="st-toggle">${stereoPlaying ? '⏸ Pause Stereo' : '▶ Play Background Stereo'}</button>
        <button class="mini-btn" id="st-bt">Bluetooth Output Ready</button>
      </div>
    `;
    inspSpecial.querySelector('#st-toggle').addEventListener('click', () => { toggleStereo(); renderSpecialPanel(node); });
    inspSpecial.querySelector('#st-bt').addEventListener('click', () => showToast('Routes through your active Windows / Bluetooth speaker output!'));
  } else if (node.category === 'hardware' && node.id.includes('printers')) {
    inspSpecial.classList.remove('hidden');
    inspSpecial.innerHTML = `
      <div class="special-title">3D PRINTER FARM — CYBER-PHYSICAL TELEMETRY</div>
      <div class="special-row">
        <button class="mini-btn accent" id="pr-test">⚡ Test Extruder Pulse</button>
      </div>
    `;
    inspSpecial.querySelector('#pr-test').addEventListener('click', () => {
      printerSweepUntil = performance.now() + 3000;
      showToast('Printer #1 test sweep triggered in 3D Studio!');
    });
  } else if (node.category === 'routines') {
    inspSpecial.classList.remove('hidden');
    inspSpecial.innerHTML = `
      <div class="special-title">ONE-CLICK APARTMENT ROUTINES</div>
      <div class="special-row">
        <button class="mini-btn accent" id="rt-build">⚡ Studio Build Routine</button>
        <button class="mini-btn" id="rt-lounge">🌙 Guest Lounge Routine</button>
      </div>
    `;
    inspSpecial.querySelector('#rt-build').addEventListener('click', () => {
      applyMood('studio');
      if (!stereoPlaying) toggleStereo();
      selectNode('apt://studio/white-cube-shelf/shelf-2', true);
      showToast('Studio Build Routine active!');
    });
    inspSpecial.querySelector('#rt-lounge').addEventListener('click', () => {
      applyMood('lounge');
      if (!stereoPlaying) toggleStereo();
      selectNode('apt://living/tv', true);
      showToast('Guest Lounge Routine active!');
    });
  } else if (node.category === 'guests') {
    inspSpecial.classList.remove('hidden');
    inspSpecial.innerHTML = `
      <div class="special-title">FRONT DOOR — GUESTS &amp; DOORMAN PRIVACY</div>
      <div class="special-row">
        <button class="mini-btn accent" id="gt-preview">${guestMode ? 'Exit Guest Preview' : 'Preview Guest View (Locks Vault & Studio)'}</button>
      </div>
    `;
    inspSpecial.querySelector('#gt-preview').addEventListener('click', () => toggleGuestMode());
  }
}

// Phase 2: Local Folder Browser inside Inspector
async function loadFolderListing(folderPath) {
  fsList.innerHTML = '';
  if (!folderPath) {
    fsList.innerHTML = '<li class="item-row"><div class="item-sub">Mount any local folder (e.g. docs, scripts, or C:\\Users\\...) to browse real PC files right on this shelf.</div></li>';
    return;
  }
  const res = await fetch(`/api/fs/list?path=${encodeURIComponent(folderPath)}`).then((r) => r.json());
  if (!res.ok) {
    fsList.innerHTML = `<li class="item-row"><div class="item-sub">${res.error}</div></li>`;
    return;
  }
  currentFsFolder = res.folder;
  currentFsParent = res.parent;
  inputMountFolder.value = res.folder;

  for (const ent of res.entries.slice(0, 35)) {
    const li = document.createElement('li');
    li.className = 'item-row';
    li.innerHTML = `
      <div class="item-main">
        <div class="item-name">${ent.is_dir ? '📁 ' : '📄 '}${ent.name}</div>
        <div class="item-sub">${ent.is_dir ? 'Folder' : `${ent.size_kb} KB`}</div>
      </div>
      <div class="row-actions">
        <button class="btn-open">${ent.is_dir ? 'Into' : 'Open'}</button>
        ${ent.is_dir ? '' : '<button class="btn-open" data-pin="1">Pin</button>'}
      </div>
    `;
    li.querySelector('.btn-open').addEventListener('click', async () => {
      if (ent.is_dir) loadFolderListing(ent.path);
      else {
        const r = await apiPost('/api/open-local', { path: ent.path });
        showToast(r.ok ? `Opened on PC: ${ent.name}` : (r.error || 'Could not open'));
      }
    });
    const pinBtn = li.querySelector('[data-pin]');
    if (pinBtn) {
      pinBtn.addEventListener('click', async () => {
        if (!selectedNodeId) return;
        const r = await apiPost('/api/node/add-file', { node_id: selectedNodeId, name: ent.name, path: ent.path, type: 'file' });
        if (r.graph) { homeGraph = r.graph; refreshUI(true); showToast(`Pinned ${ent.name} to this shelf!`); }
      });
    }
    fsList.appendChild(li);
  }
}

document.getElementById('form-mount-folder').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!selectedNodeId) return;
  const folder = inputMountFolder.value.trim();
  const r = await apiPost('/api/node/mount-folder', { node_id: selectedNodeId, folder });
  if (r.graph) {
    homeGraph = r.graph;
    loadFolderListing(folder);
    showToast(`Mounted folder to ${selectedNodeId}!`);
  }
});

document.getElementById('btn-fs-up').addEventListener('click', () => {
  if (currentFsParent && currentFsParent !== currentFsFolder) loadFolderListing(currentFsParent);
});

function selectNode(nodeId, fly = true) {
  const node = homeGraph.nodes.find((n) => n.id === nodeId);
  if (!node) return;
  selectedNodeId = node.id;
  agentContext.textContent = `Context: ${node.label} (${node.room})`;

  highlightGroup.position.set(node.position_threejs[0], Math.max(0.03, node.position_threejs[1] - 0.14), node.position_threejs[2]);
  highlightGroup.visible = true;

  if (fly && node.camera_view) {
    flyCameraTo(node.camera_view.pos, node.camera_view.look);
  }

  inspRoom.textContent = node.room;
  inspPrivacy.textContent = (node.privacy || 'private').toUpperCase();
  inspPrivacy.className = `tag-priv ${node.privacy === 'public' ? 'public' : ''}`;
  inspTitle.textContent = node.label;
  inspUri.textContent = node.id;
  inspNotes.value = node.notes || '';

  // Shelf photo preview
  if (node.photo) {
    shelfPhotoImg.src = `../${node.photo}?t=${Date.now()}`;
    shelfPhotoWrap.classList.remove('hidden');
  } else {
    shelfPhotoWrap.classList.add('hidden');
  }

  renderSpecialPanel(node);

  // Physical items
  const items = node.physical_items || [];
  atomsCount.textContent = String(items.length);
  atomsList.innerHTML = '';
  items.forEach((it, idx) => {
    const li = document.createElement('li');
    li.className = 'item-row';
    li.innerHTML = `
      <div class="item-main">
        <div class="item-name">${it.name}</div>
        <div class="item-sub">${(it.tags || []).map((t) => `#${t}`).join(' ')}</div>
      </div>
      <span class="item-qty">×${it.qty || 1}</span>
      <button class="btn-del" title="Remove">✕</button>
    `;
    li.querySelector('.btn-del').addEventListener('click', async () => {
      const r = await apiPost('/api/node/delete-item', { node_id: node.id, index: idx });
      if (r.graph) { homeGraph = r.graph; refreshUI(true); }
    });
    atomsList.appendChild(li);
  });

  // Digital files
  const files = node.digital_files || [];
  bitsCount.textContent = String(files.length);
  bitsList.innerHTML = '';
  files.forEach((f, idx) => {
    const li = document.createElement('li');
    li.className = 'item-row';
    li.innerHTML = `
      <div class="item-main">
        <div class="item-name">${f.name}</div>
        <div class="item-sub">${f.path}</div>
      </div>
      <div class="row-actions">
        <button class="btn-open">Open</button>
        <button class="btn-del" title="Remove">✕</button>
      </div>
    `;
    li.querySelector('.btn-open').addEventListener('click', () => openDigitalArtifact(f));
    li.querySelector('.btn-del').addEventListener('click', async () => {
      const r = await apiPost('/api/node/delete-file', { node_id: node.id, index: idx });
      if (r.graph) { homeGraph = r.graph; refreshUI(true); }
    });
    bitsList.appendChild(li);
  });

  // Mounted folder
  inputMountFolder.value = node.mounted_folder || '';
  loadFolderListing(node.mounted_folder || '');

  // Phase 3: Live Hardware Devices
  const devs = node.live_devices || [];
  devCount.textContent = String(devs.length);
  devList.innerHTML = '';
  devs.forEach((dev, idx) => {
    const li = document.createElement('li');
    li.className = 'item-row';
    li.innerHTML = `
      <div class="item-main">
        <div class="item-name">⚡ ${dev.label || dev.type}</div>
        <div class="item-sub">${dev.type} · ${dev.endpoint || 'Simulated (no LAN IP set)'}</div>
      </div>
      <button class="btn-open">Trigger</button>
    `;
    li.querySelector('.btn-open').addEventListener('click', async () => {
      const r = await apiPost('/api/device/trigger', { node_id: node.id, index: idx, action: 'pulse' });
      showToast(r.message || r.error || 'Triggered!', 3800);
    });
    devList.appendChild(li);
  });

  inspector.classList.remove('hidden');
  renderSidebar();
}

async function openDigitalArtifact(f) {
  if (f.path.startsWith('stereo://')) {
    document.getElementById('stereo-mode').value = f.path.replace('stereo://', '');
    if (!stereoPlaying) toggleStereo();
    showToast(`Playing ${f.name} on Music Nook Stereo!`);
    return;
  }
  if (f.type === 'youtube' || f.path.includes('youtube.com/embed')) {
    openMediaLightbox(f.name, `<iframe src="${f.path}?autoplay=1" allow="autoplay; encrypted-media" allowfullscreen></iframe>`);
    return;
  }
  if (f.type === 'image' || /\.(png|jpg|jpeg|webp)$/i.test(f.path)) {
    openMediaLightbox(f.name, `<img src="../${f.path}" alt="${f.name}" />`);
    return;
  }
  if (f.path.startsWith('http://') || f.path.startsWith('https://')) {
    window.open(f.path, '_blank', 'noopener');
    return;
  }
  const res = await apiPost('/api/open-local', { path: f.path });
  if (res.ok) showToast(`Opened on your PC: ${res.opened}`);
  else showToast(res.error || 'Could not open local file');
}

function refreshUI(keepSelected = true) {
  buildPins();
  renderSidebar();
  if (keepSelected && selectedNodeId) selectNode(selectedNodeId, false);
}

// Photo Capture + Quick Maker Chips
document.getElementById('input-shelf-photo').addEventListener('change', async (e) => {
  const file = e.target.files?.[0];
  if (!file || !selectedNodeId) return;
  showToast('Uploading shelf photo...');
  const dataUrl = await readFileAsDataUrl(file);
  const res = await apiPost('/api/node/photo', { node_id: selectedNodeId, data_url: dataUrl, auto_detect: true });
  if (res.ok) {
    homeGraph = res.graph;
    refreshUI(true);
    const nDet = (res.detected || []).length;
    showToast(nDet ? `Photo saved + Gemini Vision auto-tagged ${nDet} hardware items!` : 'Drawer photo saved to shelf! Use quick chips or +Add to tag items.', 4000);
  }
});

shelfPhotoImg.addEventListener('click', () => {
  if (shelfPhotoImg.src) openMediaLightbox('Real Drawer / Shelf Photo', `<img src="${shelfPhotoImg.src}" />`);
});

document.querySelectorAll('#maker-quick-chips .qchip').forEach((btn) => {
  btn.addEventListener('click', async () => {
    if (!selectedNodeId) return;
    const name = btn.dataset.item;
    const r = await apiPost('/api/node/add-item', { node_id: selectedNodeId, name, qty: 1 });
    if (r.graph) { homeGraph = r.graph; refreshUI(true); showToast(`Quick-added ${name}!`, 1800); }
  });
});

// Inspector Forms
document.getElementById('form-add-item').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!selectedNodeId) return;
  const name = document.getElementById('input-item-name').value.trim();
  const qty = Number(document.getElementById('input-item-qty').value) || 1;
  if (!name) return;
  const r = await apiPost('/api/node/add-item', { node_id: selectedNodeId, name, qty });
  if (r.graph) {
    homeGraph = r.graph;
    document.getElementById('input-item-name').value = '';
    document.getElementById('input-item-qty').value = '1';
    refreshUI(true);
    showToast(`Added "${name}" (×${qty}) to Home Graph!`);
  }
});

document.getElementById('form-add-file').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!selectedNodeId) return;
  const name = document.getElementById('input-file-name').value.trim();
  const path = document.getElementById('input-file-path').value.trim() || name;
  if (!name) return;
  const r = await apiPost('/api/node/add-file', { node_id: selectedNodeId, name, path, type: 'file' });
  if (r.graph) {
    homeGraph = r.graph;
    document.getElementById('input-file-name').value = '';
    document.getElementById('input-file-path').value = '';
    refreshUI(true);
    showToast(`Saved "${name}" to ${selectedNodeId}!`);
  }
});

document.getElementById('form-add-device').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!selectedNodeId) return;
  const type = document.getElementById('input-dev-type').value;
  const label = document.getElementById('input-dev-label').value.trim();
  const endpoint = document.getElementById('input-dev-ep').value.trim();
  const r = await apiPost('/api/node/device', { node_id: selectedNodeId, type, label, endpoint });
  if (r.graph) {
    homeGraph = r.graph;
    document.getElementById('input-dev-label').value = '';
    document.getElementById('input-dev-ep').value = '';
    refreshUI(true);
    showToast(`Linked ${label} (${type}) to ${selectedNodeId}!`);
  }
});

document.getElementById('btn-save-notes').addEventListener('click', async () => {
  if (!selectedNodeId) return;
  const r = await apiPost('/api/node/notes', { node_id: selectedNodeId, notes: inspNotes.value });
  if (r.graph) { homeGraph = r.graph; showToast('Spatial notes saved!'); }
});

document.getElementById('insp-close').addEventListener('click', () => {
  inspector.classList.add('hidden');
  highlightGroup.visible = false;
  selectedNodeId = null;
  agentContext.textContent = 'Context: Full Apartment';
  renderSidebar();
});

// ---------------------------------------------------------------------------
// Phase 4: Room-Aware Spatial Agent Co-Pilot
// ---------------------------------------------------------------------------
function toggleAgentDrawer() {
  agentDrawer.classList.toggle('hidden');
  document.getElementById('btn-agent-toggle').classList.toggle('on', !agentDrawer.classList.contains('hidden'));
  if (!agentDrawer.classList.contains('hidden')) agentInput.focus();
}
document.getElementById('btn-agent-toggle').addEventListener('click', toggleAgentDrawer);
document.getElementById('agent-close').addEventListener('click', toggleAgentDrawer);

function appendAgentMsg(text, who) {
  const div = document.createElement('div');
  div.className = `agent-msg ${who}`;
  div.textContent = text;
  agentLog.appendChild(div);
  agentLog.scrollTop = agentLog.scrollHeight;
}

async function sendToAgent(msg) {
  if (!msg || !String(msg).trim()) return;
  appendAgentMsg(msg, 'user');
  const res = await apiPost('/api/agent', { message: msg, node_id: selectedNodeId });
  if (res.graph) { homeGraph = res.graph; refreshUI(false); }
  appendAgentMsg(res.reply || 'Done.', 'bot');
  if (res.node_id) {
    const node = homeGraph.nodes.find((n) => n.id === res.node_id);
    if (!(guestMode && node?.privacy === 'private')) selectNode(res.node_id, true);
  }
}

document.getElementById('agent-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const txt = agentInput.value.trim();
  agentInput.value = '';
  sendToAgent(txt);
});
document.querySelectorAll('#agent-drawer .agent-chips .chip-btn').forEach((b) => {
  b.addEventListener('click', () => { if (b.dataset.q) sendToAgent(b.dataset.q); });
});

// ---------------------------------------------------------------------------
// Global Spatial Search & Command Bar
// ---------------------------------------------------------------------------
async function runCommand(text) {
  if (!text.trim()) return;
  const res = await apiPost('/api/command', { command: text });
  if (res.graph) { homeGraph = res.graph; refreshUI(false); }
  showToast(res.message || 'Done', 4200);
  cmdResults.classList.add('hidden');
  if (res.node_id) {
    const node = homeGraph.nodes.find((n) => n.id === res.node_id);
    if (guestMode && node?.privacy === 'private') {
      showToast('That match is in a Private room — switch to Owner View to inspect it.');
    } else {
      selectNode(res.node_id, true);
      // Auto-fire Pick-to-Light WLED if configured on the found shelf!
      const wledIdx = (node?.live_devices || []).findIndex((d) => d.type === 'wled_pick_to_light' && d.endpoint);
      if (wledIdx >= 0) apiPost('/api/device/trigger', { node_id: node.id, index: wledIdx, action: 'pulse' }).catch(() => {});
    }
  }
}

cmdInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { runCommand(cmdInput.value); cmdInput.blur(); }
  else if (e.key === 'Escape') { cmdResults.classList.add('hidden'); cmdInput.blur(); }
});

cmdInput.addEventListener('input', () => {
  const q = cmdInput.value.trim().toLowerCase();
  if (!q || q.startsWith('add ') || q.startsWith('put ') || q.startsWith('save ') || q.startsWith('bom ')) {
    cmdResults.classList.add('hidden');
    return;
  }
  const matches = [];
  for (const n of homeGraph.nodes) {
    if (guestMode && n.privacy === 'private') continue;
    const itemHits = (n.physical_items || []).filter((i) => `${i.name} ${(i.tags || []).join(' ')}`.toLowerCase().includes(q));
    const fileHits = (n.digital_files || []).filter((f) => `${f.name} ${f.path}`.toLowerCase().includes(q));
    const selfHit = `${n.label} ${n.room} ${n.id} ${n.notes || ''}`.toLowerCase().includes(q);
    if (selfHit || itemHits.length || fileHits.length) matches.push({ n, itemHits, fileHits });
  }
  if (!matches.length) {
    cmdResults.innerHTML = `<div class="cmd-hit"><div class="cmd-hit-title">Press Enter to run natural-language command</div><div class="cmd-hit-sub">e.g. "put ESP32 x4 on studio shelf 2" or "bom smart lamp"</div></div>`;
  } else {
    cmdResults.innerHTML = matches.slice(0, 6).map((m) => `
      <div class="cmd-hit" data-nid="${m.n.id}">
        <div class="cmd-hit-title">${m.n.label}</div>
        <div class="cmd-hit-sub">${m.n.room} · ${m.n.id}</div>
        ${m.itemHits.length ? `<div class="cmd-hit-match">Atoms: ${m.itemHits.map((i) => i.name).join(', ')}</div>` : ''}
        ${m.fileHits.length ? `<div class="cmd-hit-match">Bits: ${m.fileHits.map((f) => f.name).join(', ')}</div>` : ''}
      </div>
    `).join('');
    cmdResults.querySelectorAll('.cmd-hit[data-nid]').forEach((el) => {
      el.addEventListener('click', () => { cmdResults.classList.add('hidden'); selectNode(el.dataset.nid, true); });
    });
  }
  cmdResults.classList.remove('hidden');
});

window.addEventListener('keydown', (e) => {
  const tag = document.activeElement?.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA') return;
  if (e.key === '/' || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k')) {
    e.preventDefault(); cmdInput.focus(); cmdInput.select();
  }
  if (e.key === 'Tab') { e.preventDefault(); toggleAgentDrawer(); }
  if (e.code === 'KeyP') toggleScanCloud();
});

// Raycast Click Selection of Apartment Pins
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let downPos = { x: 0, y: 0 };
renderer.domElement.addEventListener('pointerdown', (e) => { downPos = { x: e.clientX, y: e.clientY }; });
renderer.domElement.addEventListener('pointerup', (e) => {
  if (Math.hypot(e.clientX - downPos.x, e.clientY - downPos.y) > 6) return;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(pinMeshes, false);
  if (hits.length > 0) selectNode(hits[0].object.userData.nodeId, true);
});

// Sidebar Controls
function toggleGuestMode() {
  guestMode = !guestMode;
  const btn = document.getElementById('btn-guest-mode');
  btn.textContent = guestMode ? 'Guest View' : 'Owner View';
  btn.classList.toggle('active', guestMode);
  if (guestMode && selectedNodeId) {
    const cur = homeGraph.nodes.find((n) => n.id === selectedNodeId);
    if (cur?.privacy === 'private') {
      inspector.classList.add('hidden'); highlightGroup.visible = false; selectedNodeId = null;
    }
  }
  refreshUI(true);
  showToast(guestMode ? 'Guest View: Hall Closet Vault & Studio Office locked!' : 'Owner View: All private rooms unlocked.');
}
document.getElementById('btn-guest-mode').addEventListener('click', toggleGuestMode);

function toggleScanCloud() {
  scanVisible = !scanVisible;
  if (scanCloud) scanCloud.visible = scanVisible;
  document.getElementById('btn-scan-toggle').classList.toggle('active', scanVisible);
  showToast(scanVisible ? 'COLMAP 3D Video Scan Overlay: ON' : 'COLMAP 3D Video Scan Overlay: OFF', 1800);
}
document.getElementById('btn-scan-toggle').addEventListener('click', toggleScanCloud);
document.getElementById('btn-cam-iso').addEventListener('click', () => {
  if (walkMode) exitWalkMode();
  flyCameraTo([2.4, 8.8, 3.8], [-0.6, 0.8, -0.5]);
});
document.getElementById('btn-cam-studio').addEventListener('click', () => {
  if (walkMode) exitWalkMode();
  flyCameraTo([-0.9, 2.4, 2.4], [-2.9, 0.9, 4.8]);
});

// ---------------------------------------------------------------------------
// Phase 6: Seamless First-Person Walk Mode [V], Voice Commands [🎙], & Setup
// ---------------------------------------------------------------------------
const fpControls = new PointerLockControls(camera, document.body);
const walkHud = document.getElementById('walk-hud');
const walkPrompt = document.getElementById('walk-prompt');
const walkKeys = {};
let walkMode = false;

function enterWalkMode() {
  walkMode = true;
  flyAnim = null;
  controls.enabled = false;
  if (ceilingMesh) ceilingMesh.visible = true;
  camera.position.set(-0.6, 1.62, -3.5);
  camera.lookAt(-1.8, 1.35, -6.2);
  walkHud.classList.remove('hidden');
  document.getElementById('btn-walk-mode').textContent = '🏠 Dollhouse [V]';
  fpControls.lock();
}

function exitWalkMode() {
  walkMode = false;
  if (fpControls.isLocked) fpControls.unlock();
  walkHud.classList.add('hidden');
  if (ceilingMesh) ceilingMesh.visible = false;
  controls.enabled = true;
  document.getElementById('btn-walk-mode').textContent = '🚶 Walk [V]';
}

fpControls.addEventListener('unlock', () => {
  if (walkMode) exitWalkMode();
});

document.getElementById('btn-walk-mode').addEventListener('click', () => {
  if (walkMode) exitWalkMode();
  else enterWalkMode();
});

window.addEventListener('keydown', (e) => {
  walkKeys[e.code] = true;
  const tag = document.activeElement?.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA') return;
  if (e.code === 'KeyV') {
    e.preventDefault();
    if (walkMode) exitWalkMode();
    else enterWalkMode();
  }
  if (walkMode && e.code === 'KeyE') {
    const nearest = findNearestNodeToCamera();
    if (nearest) {
      exitWalkMode();
      selectNode(nearest.id, false);
    }
  }
});
window.addEventListener('keyup', (e) => { walkKeys[e.code] = false; });

function findNearestNodeToCamera() {
  let best = null;
  let bestD = 2.4;
  const p = camera.position;
  for (const n of homeGraph.nodes) {
    if (guestMode && n.privacy === 'private') continue;
    const d = p.distanceTo(new THREE.Vector3(...n.position_threejs));
    if (d < bestD) { bestD = d; best = n; }
  }
  return best;
}

// Voice Command Recognition (Web Speech API)
const btnVoice = document.getElementById('btn-voice');
const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRec) {
  const rec = new SpeechRec();
  rec.lang = 'en-US';
  rec.interimResults = false;
  btnVoice.addEventListener('click', () => {
    btnVoice.classList.add('listening');
    showToast('🎙 Listening... speak a command like "where is basys" or "put LED strip on studio shelf 3"', 4000);
    try { rec.start(); } catch (_) {}
  });
  rec.onresult = (ev) => {
    const spoken = ev.results[0][0].transcript;
    cmdInput.value = spoken;
    runCommand(spoken);
  };
  rec.onend = () => btnVoice.classList.remove('listening');
  rec.onerror = () => { btnVoice.classList.remove('listening'); showToast('Voice input stopped — check browser microphone permissions.'); };
} else {
  btnVoice.addEventListener('click', () => showToast('Web Speech API works best in Chrome or Edge.'));
}

// Settings, Gemini API Key, Hardware Poll & Graph Export Modal
const settingsModal = document.getElementById('settings-modal');
const geminiStatusEl = document.getElementById('gemini-status');
const hwPollList = document.getElementById('hw-poll-list');

document.getElementById('btn-settings').addEventListener('click', async () => {
  settingsModal.classList.remove('hidden');
  try {
    const h = await fetch('/api/health').then((r) => r.json());
    geminiStatusEl.textContent = h.ollama_enabled
      ? `Ollama: ${h.ollama_model} ✓`
      : (h.gemini_enabled ? 'Gemini 2.5 Active ✓' : 'Local Offline Mode');
  } catch (_) {}
});
document.getElementById('settings-close').addEventListener('click', () => settingsModal.classList.add('hidden'));

document.getElementById('form-gemini-key').addEventListener('submit', async (e) => {
  e.preventDefault();
  const key = document.getElementById('input-gemini-key').value.trim();
  const r = await apiPost('/api/config/gemini', { api_key: key });
  document.getElementById('input-gemini-key').value = '';
  geminiStatusEl.textContent = r.gemini_enabled ? 'Gemini 2.5 Active ✓' : 'Local Offline Mode';
  showToast(r.gemini_enabled ? 'Saved GEMINI_API_KEY to local .env (gitignored)!' : 'Cleared key — running in offline local mode.');
});

document.getElementById('btn-poll-hw').addEventListener('click', async () => {
  hwPollList.innerHTML = '<li class="item-row"><div class="item-sub">Polling LAN devices...</div></li>';
  const r = await fetch('/api/hardware/poll').then((x) => x.json());
  hwPollList.innerHTML = '';
  if (!r.devices?.length) {
    hwPollList.innerHTML = '<li class="item-row"><div class="item-sub">No LAN IPs linked yet. Click any shelf or printer and add an IP in "Live Hardware Bridge".</div></li>';
    return;
  }
  for (const d of r.devices) {
    const li = document.createElement('li');
    li.className = 'item-row';
    li.innerHTML = `<div class="item-main"><div class="item-name">${d.status === 'online' ? '🟢' : '🔴'} ${d.label}</div><div class="item-sub">${d.type} · ${d.detail || d.status}</div></div>`;
    hwPollList.appendChild(li);
  }
});

document.getElementById('btn-export-graph').addEventListener('click', () => {
  const blob = new Blob([JSON.stringify(homeGraph, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `vaughn_apt_home_graph_${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  showToast('Exported home_graph.json backup!');
});

document.querySelectorAll('.mood-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    applyMood(btn.dataset.mood);
    apiPost('/api/mood', { mood: btn.dataset.mood }).catch(() => {});
  });
});

// Persistent Stereo Engine
let stereoCtx = null;
let stereoGain = null;
let stereoTimer = null;
let stereoPlaying = false;
const CHORDS = {
  lofi: [[261.63, 329.63, 392.0, 493.88], [220.0, 261.63, 329.63, 392.0], [174.61, 220.0, 261.63, 329.63], [196.0, 246.94, 293.66, 349.23]],
  focus: [[130.81, 196.0, 293.66, 329.63], [146.83, 220.0, 293.66, 349.23], [110.0, 164.81, 246.94, 329.63]],
  cosmic: [[196.0, 293.66, 369.99, 440.0], [164.81, 246.94, 329.63, 392.0], [146.83, 220.0, 293.66, 369.99]],
};
let chordIdx = 0;

function playAmbientChord() {
  if (!stereoCtx || !stereoPlaying) return;
  const mode = document.getElementById('stereo-mode').value;
  const notes = CHORDS[mode][chordIdx % CHORDS[mode].length];
  chordIdx++;
  const now = stereoCtx.currentTime;
  notes.forEach((f, i) => {
    const osc = stereoCtx.createOscillator();
    const g = stereoCtx.createGain();
    osc.type = mode === 'lofi' ? 'triangle' : 'sine';
    osc.frequency.value = f;
    g.gain.setValueAtTime(0.0001, now + i * 0.06);
    g.gain.linearRampToValueAtTime(0.09, now + 0.6 + i * 0.06);
    g.gain.exponentialRampToValueAtTime(0.0008, now + 3.4);
    osc.connect(g); g.connect(stereoGain);
    osc.start(now + i * 0.06);
    osc.stop(now + 3.5);
  });
}

function toggleStereo() {
  stereoPlaying = !stereoPlaying;
  const btn = document.getElementById('stereo-play-btn');
  const sub = document.getElementById('stereo-track');
  if (stereoPlaying) {
    if (!stereoCtx) {
      stereoCtx = new (window.AudioContext || window.webkitAudioContext)();
      stereoGain = stereoCtx.createGain();
      stereoGain.gain.value = Number(document.getElementById('stereo-vol').value) / 100;
      stereoGain.connect(stereoCtx.destination);
    }
    btn.textContent = '⏸';
    sub.textContent = 'Playing across apartment · Persistent';
    playAmbientChord();
    stereoTimer = setInterval(playAmbientChord, 3200);
  } else {
    btn.textContent = '▶';
    sub.textContent = 'Paused · Click to resume';
    clearInterval(stereoTimer);
  }
}
document.getElementById('stereo-play-btn').addEventListener('click', toggleStereo);
document.getElementById('stereo-vol').addEventListener('input', (e) => {
  if (stereoGain) stereoGain.gain.value = Number(e.target.value) / 100;
});

// ---------------------------------------------------------------------------
// Phase 5: Live 3D Multiplayer Guest Avatars, Doorbell Comms & Co-Watch Sync
// ---------------------------------------------------------------------------
const urlParams = new URLSearchParams(window.location.search);
const myClientId = `u_${Math.random().toString(36).slice(2, 9)}`;
const myDisplayName = urlParams.get('name') || (guestMode ? `Guest-${myClientId.slice(-3).toUpperCase()}` : 'Vaughn (Owner)');
const guestsDrawer = document.getElementById('guests-drawer');
const guestCountEl = document.getElementById('guest-count');
const visitorsListEl = document.getElementById('visitors-list');
const inboxListEl = document.getElementById('inbox-list');
const loungeChatLog = document.getElementById('lounge-chat-log');
const loungeChatInput = document.getElementById('lounge-chat-input');
const cowatchBanner = document.getElementById('cowatch-banner');
const cowatchText = document.getElementById('cowatch-text');
let lastSharedTvTs = 0;
let activeSharedTv = null;
let studioUnlocked = false;

const avatarGroup = new THREE.Group();
scene.add(avatarGroup);
const avatarMap = new Map(); // id -> { group, targetPos }

function makeNameSprite(label, colHex) {
  const cvs = document.createElement('canvas');
  cvs.width = 256; cvs.height = 64;
  const ctx = cvs.getContext('2d');
  ctx.fillStyle = 'rgba(10, 16, 26, 0.85)';
  ctx.beginPath(); ctx.roundRect(8, 10, 240, 44, 14); ctx.fill();
  ctx.strokeStyle = colHex; ctx.lineWidth = 3; ctx.stroke();
  ctx.fillStyle = '#f0f6fc'; ctx.font = 'bold 22px Segoe UI, sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(label, 128, 33);
  const tex = new THREE.CanvasTexture(cvs);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true }));
  sp.scale.set(0.95, 0.24, 1);
  sp.position.y = 1.65;
  return sp;
}

function syncAvatars(visitors) {
  guestCountEl.textContent = String(visitors.length);
  const alive = new Set();
  visitorsListEl.innerHTML = '';

  for (const v of visitors) {
    const li = document.createElement('li');
    li.className = 'item-row';
    li.innerHTML = `
      <div class="item-main">
        <div class="item-name"><span style="color:${v.color}">●</span> ${v.name} ${v.id === myClientId ? '(You)' : ''}</div>
        <div class="item-sub">${v.role.toUpperCase()} · ${v.room}</div>
      </div>
    `;
    visitorsListEl.appendChild(li);

    if (v.id === myClientId) continue;
    alive.add(v.id);
    if (!avatarMap.has(v.id)) {
      const grp = new THREE.Group();
      const col = new THREE.Color(v.color || '#7ee787');
      const body = new THREE.Mesh(
        new THREE.CapsuleGeometry(0.18, 0.55, 8, 16),
        new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.45, roughness: 0.3 })
      );
      body.position.y = 0.72;
      const head = new THREE.Mesh(
        new THREE.SphereGeometry(0.16, 16, 16),
        new THREE.MeshStandardMaterial({ color: 0xf4f8ff, emissive: col, emissiveIntensity: 0.25 })
      );
      head.position.y = 1.24;
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(0.24, 0.32, 24),
        new THREE.MeshBasicMaterial({ color: col, side: THREE.DoubleSide, transparent: true, opacity: 0.7 })
      );
      ring.rotation.x = -Math.PI / 2; ring.position.y = 0.03;
      grp.add(body, head, ring, makeNameSprite(v.name, v.color || '#7ee787'));
      grp.position.set(v.pos[0], 0, v.pos[2]);
      avatarGroup.add(grp);
      avatarMap.set(v.id, { group: grp, targetPos: new THREE.Vector3(v.pos[0], 0, v.pos[2]) });
    } else {
      avatarMap.get(v.id).targetPos.set(v.pos[0], 0, v.pos[2]);
    }
  }
  for (const [id, entry] of avatarMap.entries()) {
    if (!alive.has(id)) {
      avatarGroup.remove(entry.group);
      avatarMap.delete(id);
    }
  }
}

function renderLoungeChat(messages) {
  loungeChatLog.innerHTML = '';
  for (const m of messages) {
    const d = document.createElement('div');
    d.className = `agent-msg ${m.sender === myDisplayName ? 'user' : 'bot'}`;
    d.textContent = `${m.sender}: ${m.text}`;
    loungeChatLog.appendChild(d);
  }
  loungeChatLog.scrollTop = loungeChatLog.scrollHeight;
}

function playDoorbellChime() {
  try {
    const ctx = stereoCtx || new (window.AudioContext || window.webkitAudioContext)();
    [[659.25, 0], [523.25, 0.22]].forEach(([f, delay]) => {
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = 'sine'; osc.frequency.value = f;
      g.gain.setValueAtTime(0.16, ctx.currentTime + delay);
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + 0.55);
      osc.connect(g); g.connect(ctx.destination);
      osc.start(ctx.currentTime + delay); osc.stop(ctx.currentTime + delay + 0.58);
    });
  } catch (_) {}
}

function renderInbox(inbox) {
  inboxListEl.innerHTML = '';
  for (const m of inbox) {
    const li = document.createElement('li');
    li.className = 'item-row';
    const tierCls = m.tier === 'vip' ? 'tier-vip' : (m.tier === 'muted' ? 'tier-muted' : 'tier-standard');
    li.innerHTML = `
      <div class="item-main">
        <div class="item-name">[${m.channel}] ${m.from}</div>
        <div class="item-sub">${m.subject} · <span class="${tierCls}">${m.status.replace('_', ' ').toUpperCase()}</span></div>
      </div>
      <button class="btn-del" title="Dismiss">✕</button>
    `;
    li.querySelector('.btn-del').addEventListener('click', async () => {
      const r = await apiPost('/api/inbox/dismiss', { id: m.id });
      if (r.inbox) renderInbox(r.inbox);
    });
    inboxListEl.appendChild(li);
  }
}

async function fetchGraphFromServer() {
  const g = await fetch(`/api/graph${guestMode ? '?guest=1' : ''}`).then((r) => r.json());
  homeGraph = g;
  studioUnlocked = Boolean(g.studio_unlocked);
  const uBtn = document.getElementById('btn-unlock-studio');
  if (uBtn) {
    uBtn.textContent = studioUnlocked ? '🔓 Studio Unlocked' : '🔒 Studio Locked';
    uBtn.classList.toggle('active', studioUnlocked);
    uBtn.style.display = guestMode ? 'none' : '';
  }
  applyMood(g.lighting_mood || 'afternoon');
  if (g.custom_wall_art) applyWallArtTexture(g.custom_wall_art);
  if (g.comms_inbox) renderInbox(g.comms_inbox);
  buildPins();
  renderSidebar();
}

async function sendPresenceHeartbeat() {
  try {
    const cur = homeGraph.nodes.find((n) => n.id === selectedNodeId);
    const pos = cur ? cur.position_threejs : [controls.target.x, 1.0, controls.target.z];
    const room = cur ? cur.room : 'Corner Living Room';
    const res = await apiPost('/api/presence/heartbeat', {
      id: myClientId,
      name: myDisplayName,
      guest: guestMode,
      pos,
      room,
      color: guestMode ? '#7ee787' : '#58d5ff',
    });
    if (res.visitors) syncAvatars(res.visitors);
    if (res.chat) renderLoungeChat(res.chat);
    if (res.studio_unlocked !== undefined && res.studio_unlocked !== studioUnlocked) {
      studioUnlocked = res.studio_unlocked;
      if (guestMode) fetchGraphFromServer();
    }
    if (res.shared_tv?.embed_url && res.shared_tv.updated_at > lastSharedTvTs) {
      lastSharedTvTs = res.shared_tv.updated_at;
      activeSharedTv = res.shared_tv;
      cowatchText.textContent = `📺 ${res.shared_tv.shared_by} shared "${res.shared_tv.title}" on Living Room TV`;
      cowatchBanner.classList.remove('hidden');
    }
  } catch (_) {}
}

document.getElementById('btn-guests-toggle').addEventListener('click', () => {
  guestsDrawer.classList.toggle('hidden');
  document.getElementById('btn-guests-toggle').classList.toggle('on', !guestsDrawer.classList.contains('hidden'));
  fetch('/api/inbox').then((r) => r.json()).then((d) => { if (d.inbox) renderInbox(d.inbox); }).catch(() => {});
});
document.getElementById('guests-close').addEventListener('click', () => {
  guestsDrawer.classList.add('hidden');
  document.getElementById('btn-guests-toggle').classList.remove('on');
});
document.getElementById('btn-open-guest-tab').addEventListener('click', () => {
  const name = prompt('Guest name for the live second tab:', 'Alex') || 'Alex';
  window.open(`home_os.html?guest=1&name=${encodeURIComponent(name)}`, '_blank');
});
document.getElementById('btn-ring-doorbell').addEventListener('click', async () => {
  playDoorbellChime();
  const samples = [
    ['Maya (VIP Friend)', 'SMS', 'Coming over to hang out in the Living Room!'],
    ['Digikey Order', 'Email', 'Your Basys & sensor package arrived at lobby'],
    ['Promo Deals', 'Email', 'Unsubscribe newsletter flash sale offer'],
  ];
  const pick = samples[Math.floor(Math.random() * samples.length)];
  const r = await apiPost('/api/inbox/add', { from: pick[0], channel: pick[1], subject: pick[2] });
  if (r.inbox) {
    renderInbox(r.inbox);
    showToast(`🔔 Doorbell! Doorman triaged ${r.item.from} → ${r.item.status.replace('_', ' ').toUpperCase()}`, 4000);
  }
});
document.getElementById('btn-unlock-studio').addEventListener('click', async () => {
  const r = await apiPost('/api/guest-access', { studio_unlocked: !studioUnlocked });
  studioUnlocked = r.studio_unlocked;
  const uBtn = document.getElementById('btn-unlock-studio');
  uBtn.textContent = studioUnlocked ? '🔓 Studio Unlocked' : '🔒 Studio Locked';
  uBtn.classList.toggle('active', studioUnlocked);
  showToast(studioUnlocked ? 'Studio Office temporarily unlocked for Guests!' : 'Studio Office locked — Private to Owner.');
});
document.getElementById('lounge-chat-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = loungeChatInput.value.trim();
  if (!text) return;
  loungeChatInput.value = '';
  const r = await apiPost('/api/chat', { sender: myDisplayName, role: guestMode ? 'guest' : 'owner', text });
  if (r.chat) renderLoungeChat(r.chat);
});
document.getElementById('cowatch-join').addEventListener('click', () => {
  if (!activeSharedTv) return;
  selectNode('apt://living/tv', true);
  openMediaLightbox(activeSharedTv.title, `<iframe src="${activeSharedTv.embed_url}?autoplay=1" allow="autoplay; encrypted-media" allowfullscreen></iframe>`);
});
document.getElementById('cowatch-hide').addEventListener('click', () => cowatchBanner.classList.add('hidden'));

// ---------------------------------------------------------------------------
// Phase 13B: 3D Interior Vibe-Room Designer (Local Ollama + Collision Verifier)
// ---------------------------------------------------------------------------
const vibeRoomGroup = new THREE.Group();
scene.add(vibeRoomGroup);

function buildInteriorVibePropMesh(prop) {
  const g = new THREE.Group();
  const [bw, bh, bd] = prop.bbox || [0.8, 0.9, 0.6];
  const bodyMat = new THREE.MeshStandardMaterial({ color: prop.color || '#2a5d67', roughness: 0.45, metalness: 0.25 });
  const accentMat = new THREE.MeshStandardMaterial({
    color: prop.accent || '#00f0ff',
    emissive: prop.accent || '#00f0ff',
    emissiveIntensity: 0.55,
    roughness: 0.25,
  });

  if (prop.kind === 'lamp') {
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.06, bh * 0.85, 10), bodyMat);
    pole.position.y = bh * 0.425;
    const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.18, 12, 12), accentMat);
    bulb.position.y = bh * 0.9;
    g.add(pole, bulb);
  } else if (prop.kind === 'plant') {
    const pot = new THREE.Mesh(new THREE.CylinderGeometry(bw * 0.36, bw * 0.28, bh * 0.38, 10), new THREE.MeshStandardMaterial({ color: prop.accent || '#c87d4b', roughness: 0.7 }));
    pot.position.y = bh * 0.19;
    const crown = new THREE.Mesh(new THREE.DodecahedronGeometry(bw * 0.42, 0), bodyMat);
    crown.position.y = bh * 0.68;
    g.add(pot, crown);
  } else {
    const base = new THREE.Mesh(new THREE.BoxGeometry(bw, bh * 0.72, bd), bodyMat);
    base.position.y = bh * 0.36;
    base.castShadow = true;
    const topStrip = new THREE.Mesh(new THREE.BoxGeometry(bw * 0.92, bh * 0.14, bd * 0.85), accentMat);
    topStrip.position.y = bh * 0.82;
    g.add(base, topStrip);
  }

  g.position.set(prop.pos[0], prop.pos[1] || 0, prop.pos[2]);
  g.rotation.y = ((prop.rot_y || 0) * Math.PI) / 180;
  return g;
}

function renderVibeRoomProps(props, verifier = null) {
  while (vibeRoomGroup.children.length > 0) vibeRoomGroup.remove(vibeRoomGroup.children[0]);
  (props || []).forEach((p) => vibeRoomGroup.add(buildInteriorVibePropMesh(p)));

  const listEl = document.getElementById('vibe-room-props-list');
  const statusEl = document.getElementById('vibe-room-status');
  if (statusEl) {
    const vTxt = verifier ? (verifier.pass ? 'PASS ✅' : `WARN (${verifier.collisions.length})`) : 'READY';
    statusEl.textContent = `${(props || []).length} Interior Prop(s) · Collision Verifier: ${vTxt}`;
  }
  if (listEl) {
    listEl.innerHTML = (props || []).length
      ? props.map((p) => `<li class="item-row"><div class="item-main"><div class="item-name">${p.name}</div><div class="item-sub">${p.room} · [${p.pos.join(', ')}]</div></div></li>`).join('')
      : '<li class="item-row"><div class="item-sub">No Vibe-Room props placed yet. Pick a preset or describe what to build!</div></li>';
  }
}

async function loadVibeRoomProps() {
  try {
    const r = await fetch('/api/vibe/room-layout').then((x) => x.json());
    if (r.ok) renderVibeRoomProps(r.props, r.verifier);
  } catch (_) {}
}

async function runVibeRoomDesign(promptText) {
  const q = (promptText || '').trim();
  if (!q) return;
  const logEl = document.getElementById('vibe-room-log');
  logEl.innerHTML += `<div class="agent-msg user">${q}</div>`;
  logEl.scrollTop = logEl.scrollHeight;
  try {
    const r = await apiPost('/api/vibe/room-layout', { prompt: q });
    if (r.ok) {
      renderVibeRoomProps(r.props, r.verifier);
      logEl.innerHTML += `<div class="agent-msg bot">[${r.source}] ${r.note} (Collision: ${r.verifier?.pass ? 'PASS ✅' : 'ADJUSTED'})</div>`;
      logEl.scrollTop = logEl.scrollHeight;
      showToast(`Vibe-Room updated (${r.props.length} props · ${r.source})`);
    }
  } catch (err) {
    logEl.innerHTML += `<div class="agent-msg bot">Error: ${err.message}</div>`;
  }
}

const vibeRoomDrawer = document.getElementById('vibe-room-drawer');
document.getElementById('btn-vibe-room')?.addEventListener('click', () => {
  vibeRoomDrawer?.classList.toggle('hidden');
  loadVibeRoomProps();
});
document.getElementById('vibe-room-close')?.addEventListener('click', () => vibeRoomDrawer?.classList.add('hidden'));
document.getElementById('vibe-room-form')?.addEventListener('submit', (e) => {
  e.preventDefault();
  const inp = document.getElementById('vibe-room-input');
  const val = inp.value;
  inp.value = '';
  runVibeRoomDesign(val);
});
document.querySelectorAll('.vibe-chip').forEach((btn) => {
  btn.addEventListener('click', () => runVibeRoomDesign(btn.dataset.vp));
});
document.getElementById('btn-vibe-room-clear')?.addEventListener('click', async () => {
  const r = await apiPost('/api/vibe/room-layout/clear', {});
  if (r.ok) {
    renderVibeRoomProps([], r.verifier);
    showToast('Cleared Vibe-Room interior props.');
  }
});

// Boot
fetchGraphFromServer()
  .then(() => {
    loadVibeRoomProps();
    if (guestMode) {
      const btn = document.getElementById('btn-guest-mode');
      btn.textContent = 'Guest View';
      btn.classList.add('active');
    }
    sendPresenceHeartbeat();
    setInterval(sendPresenceHeartbeat, 2200);
  })
  .catch(() => { statsLine.textContent = 'Start scripts/home_os_server.py to enable persistence'; });

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.05);
  const t = clock.elapsedTime;
  for (const m of pinMeshes) {
    m.position.y = m.userData.baseY + Math.sin(t * 2.4 + m.userData.baseY * 4) * 0.03;
  }
  for (const entry of avatarMap.values()) {
    entry.group.position.lerp(entry.targetPos, 0.08);
    entry.group.position.y = Math.sin(t * 2.2) * 0.04;
  }
  if (highlightGroup.visible) {
    const s = 1.0 + Math.sin(t * 5.0) * 0.16;
    ringMesh.scale.set(s, s, 1);
  }
  if (printerHeadMesh && performance.now() < printerSweepUntil) {
    printerHeadMesh.position.z = 4.15 + Math.sin(t * 20) * 0.13;
  }
  if (walkMode && fpControls.isLocked) {
    const spd = (walkKeys['ShiftLeft'] || walkKeys['ShiftRight']) ? 4.2 : 2.5;
    let fwd = 0, right = 0;
    if (walkKeys['KeyW'] || walkKeys['ArrowUp']) fwd += 1;
    if (walkKeys['KeyS'] || walkKeys['ArrowDown']) fwd -= 1;
    if (walkKeys['KeyD'] || walkKeys['ArrowRight']) right += 1;
    if (walkKeys['KeyA'] || walkKeys['ArrowLeft']) right -= 1;
    if (fwd || right) {
      const len = Math.hypot(fwd, right);
      fpControls.moveForward((fwd / len) * spd * dt);
      fpControls.moveRight((right / len) * spd * dt);
      camera.position.x = Math.max(-3.65, Math.min(3.95, camera.position.x));
      camera.position.z = Math.max(-7.25, Math.min(5.75, camera.position.z));
      camera.position.y = 1.62;
    }
    const near = findNearestNodeToCamera();
    walkPrompt.innerHTML = near
      ? `Press <kbd>E</kbd> — Inspect <strong>${near.label}</strong> · <kbd>Esc</kbd> Dollhouse`
      : `WASD to walk · Mouse to look · <kbd>E</kbd> Inspect nearest zone · <kbd>Esc</kbd> Dollhouse`;
  } else {
    if (flyAnim) {
      const u = Math.min(1, (performance.now() - flyAnim.t0) / flyAnim.dur);
      const e = 1 - Math.pow(1 - u, 3);
      camera.position.lerpVectors(flyAnim.startPos, flyAnim.endPos, e);
      controls.target.lerpVectors(flyAnim.startLook, flyAnim.endLook, e);
      if (u >= 1) flyAnim = null;
    }
    controls.update();
  }
  renderer.render(scene, camera);
}
animate();
