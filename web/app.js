import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';

const EYE_HEIGHT = 1.62;
const PLAYER_RADIUS = 0.28;
const ESCAPE_PIN = '4729';

const viewport = document.getElementById('viewport');
const overlay = document.getElementById('overlay');
const hud = document.getElementById('hud');
const binoOverlay = document.getElementById('bino-overlay');
const loadStatus = document.getElementById('load-status');
const roomLabel = document.getElementById('room-label');
const timerLabel = document.getElementById('timer-label');
const clueCountEl = document.getElementById('clue-count');
const invItemsEl = document.getElementById('inv-items');
const interactPrompt = document.getElementById('interact-prompt');
const reticle = document.getElementById('reticle');
const toastEl = document.getElementById('toast');
const scanBadge = document.getElementById('scan-badge');
const flashBadge = document.getElementById('flash-badge');

const clueModal = document.getElementById('clue-modal');
const modalTag = document.getElementById('modal-tag');
const modalTitle = document.getElementById('modal-title');
const modalBody = document.getElementById('modal-body');
const modalCode = document.getElementById('modal-code');

const midiModal = document.getElementById('midi-modal');
const midiSeqEl = document.getElementById('midi-seq');
const midiStatusEl = document.getElementById('midi-status');

const keypadModal = document.getElementById('keypad-modal');
const keypadDisplay = document.getElementById('keypad-display');
const keypadMsg = document.getElementById('keypad-msg');

// Scene & Renderer
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x9ec5e8);
scene.fog = new THREE.Fog(0xb6d4ee, 20, 48);

const camera = new THREE.PerspectiveCamera(68, window.innerWidth / window.innerHeight, 0.08, 100);
camera.position.set(-0.6, EYE_HEIGHT, -4.0);
camera.lookAt(-1.8, 1.35, -6.5);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.12;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
viewport.appendChild(renderer.domElement);

// Lighting
scene.add(new THREE.HemisphereLight(0xdceeff, 0x7b634b, 0.92));

const sun = new THREE.DirectionalLight(0xfff1d6, 2.35);
sun.position.set(-10, 12, -9);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.near = 1;
sun.shadow.camera.far = 35;
const d = 10;
sun.shadow.camera.left = -d; sun.shadow.camera.right = d;
sun.shadow.camera.top = d; sun.shadow.camera.bottom = -d;
scene.add(sun);

[
  [-1.0, 2.6, -5.0, 0xfff4e0, 1.25],
  [-2.0, 2.55, 0.3, 0xffedd2, 1.05],
  [-2.1, 2.55, 4.0, 0xf2f6ff, 1.15],
  [2.0, 2.55, 3.0, 0xffeed6, 0.95],
  [2.6, 2.55, 5.0, 0xf0f8ff, 0.85],
].forEach(([x, y, z, col, inten]) => {
  const pl = new THREE.PointLight(col, inten, 8.5, 1.6);
  pl.position.set(x, y, z);
  scene.add(pl);
});

// Dual-Mode Flashlight (White LED / Purple UV Blacklight)
const flashlight = new THREE.SpotLight(0xfff6e5, 0, 12, Math.PI / 5.5, 0.45, 1.5);
flashlight.position.set(0, 0, 0);
camera.add(flashlight);
flashlight.target.position.set(0, 0, -1);
camera.add(flashlight.target);
scene.add(camera);

let lightMode = 'OFF'; // 'OFF' | 'WHITE' | 'UV'
let hasUVLens = false;
let caffeineUntil = 0;

// Controls & State
const controls = new PointerLockControls(camera, document.body);
const keys = {};
let activeModal = null;
let startTime = null;
let escaped = false;
let binocularsZoom = false;

// Animated scene refs
let printerHeadObj = null;
let printerAnimatingUntil = 0;
let uvLensMesh = null;

// Web Audio Synth
let audioCtx = null;
function playTone(freq, dur = 0.14, type = 'sine', vol = 0.12) {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(vol, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + dur);
    osc.connect(gain); gain.connect(audioCtx.destination);
    osc.start(); osc.stop(audioCtx.currentTime + dur);
  } catch (_) {}
}

function showToast(msg, ms = 3000) {
  toastEl.textContent = msg;
  toastEl.classList.remove('hidden');
  clearTimeout(toastEl._t);
  toastEl._t = setTimeout(() => toastEl.classList.add('hidden'), ms);
}

// Inventory
const inventory = [];
function addInventory(item) {
  if (inventory.includes(item)) return;
  inventory.push(item);
  invItemsEl.innerHTML = inventory.map((i) => `<span class="inv-chip">${i}</span>`).join('');
}

function setLightMode(mode) {
  lightMode = mode;
  if (mode === 'OFF') {
    flashlight.intensity = 0;
    flashBadge.textContent = 'Light [F/U]: OFF';
    flashBadge.className = 'pill';
  } else if (mode === 'WHITE') {
    flashlight.color.setHex(0xfff6e5);
    flashlight.intensity = 4.6;
    flashBadge.textContent = 'Light [F]: WHITE';
    flashBadge.className = 'pill on';
  } else if (mode === 'UV') {
    flashlight.color.setHex(0x9b30ff);
    flashlight.intensity = 6.2;
    flashBadge.textContent = 'UV Light [U]: ON';
    flashBadge.className = 'pill uv';
  }
  playTone(mode === 'OFF' ? 380 : (mode === 'UV' ? 880 : 680), 0.06);
}

// ---------------------------------------------------------------------------
// Escape Room Clues, Interactive Puzzles & Doors
// ---------------------------------------------------------------------------
const foundClues = new Set();
const interactables = [];
const doorStates = new Map();

function markClueFound(key) {
  if (!['laptop', 'music', 'printer', 'whiteboard'].includes(key)) return;
  foundClues.add(key);
  clueCountEl.textContent = String(foundClues.size);
  const li = document.querySelector(`#clue-list li[data-clue="${key}"]`);
  if (li) {
    li.classList.add('found');
    li.textContent = li.textContent.replace('☐', '☑');
  }
  const b = beacons.find((x) => x.key === key);
  if (b) b.mesh.material.color.setHex(0x7ee787);
}

function openInfoModal(tag, title, body, code) {
  modalTag.textContent = tag;
  modalTitle.textContent = title;
  modalBody.textContent = body;
  modalCode.textContent = code;
  modalCode.style.display = code ? 'block' : 'none';
  clueModal.classList.remove('hidden');
  activeModal = clueModal;
  controls.unlock();
}

// Puzzle #2: Playable MIDI C-Maj-7 Chord (C -> E -> G -> B)
const TARGET_MIDI = ['C', 'E', 'G', 'B'];
let midiProgress = [];
function openMidiModal() {
  midiProgress = [];
  midiSeqEl.textContent = 'Sequence: _ · _ · _ · _';
  midiStatusEl.textContent = foundClues.has('music')
    ? 'Already decoded! Digit #2 = 7 — play freely!'
    : 'Play C → E → G → B to unlock Digit #2';
  midiStatusEl.style.color = '#9ab0c9';
  midiModal.classList.remove('hidden');
  activeModal = midiModal;
  controls.unlock();
}

document.querySelectorAll('.pkey').forEach((btn) => {
  btn.addEventListener('click', () => {
    const note = btn.dataset.note;
    const freq = Number(btn.dataset.freq);
    playTone(freq, 0.36, 'triangle', 0.16);
    btn.classList.add('hit');
    setTimeout(() => btn.classList.remove('hit'), 150);

    const expected = TARGET_MIDI[midiProgress.length];
    if (note === expected) {
      midiProgress.push(note);
      const disp = [0, 1, 2, 3].map((i) => midiProgress[i] || '_').join(' · ');
      midiSeqEl.textContent = `Sequence: ${disp}`;
      if (midiProgress.length === TARGET_MIDI.length) {
        markClueFound('music');
        addInventory('Synth Track #2');
        midiStatusEl.textContent = 'CHORD MATCHED! Mixer LED unlocked: DIGIT #2 = 7';
        midiStatusEl.style.color = '#7ee787';
        [261.63, 329.63, 392.0, 493.88, 523.25].forEach((f, i) =>
          setTimeout(() => playTone(f, 0.55, 'triangle', 0.14), i * 80)
        );
      }
    } else {
      midiProgress = note === 'C' ? ['C'] : [];
      const disp = [0, 1, 2, 3].map((i) => midiProgress[i] || '_').join(' · ');
      midiSeqEl.textContent = `Sequence: ${disp}`;
      midiStatusEl.textContent = 'Wrong note — restart from C → E → G → B!';
      midiStatusEl.style.color = '#ff7b72';
    }
  });
});

// Puzzle #3: Animated 3D Printer + Collectible UV Lens
function trigger3DPrinter() {
  if (!hasUVLens) {
    printerAnimatingUntil = performance.now() + 2600;
    for (let i = 0; i < 8; i++) {
      setTimeout(() => playTone(280 + (i % 3) * 70, 0.08, 'square', 0.05), i * 240);
    }
    showToast('3D Printer finishing UV Lens print... watch the extruder!', 2600);
    setTimeout(() => {
      hasUVLens = true;
      if (uvLensMesh) uvLensMesh.visible = false;
      addInventory('UV Blacklight Lens [U]');
      markClueFound('printer');
      openInfoModal(
        'CLUE 3 OF 4 — STUDIO 3D PRINTER',
        'Printed UV Blacklight Filter + Calibration Tag!',
        'You collect the freshly printed violet UV Lens Filter (press [U] to activate UV Blacklight!). Stamped on the print bed underneath is the third Yale lock digit.',
        'DIGIT #3 = 2'
      );
    }, 1800);
  } else {
    openInfoModal(
      'STUDIO 3D PRINTER — COMPLETE',
      'UV Lens Filter Collected',
      'Press [U] to shine your UV Blacklight onto the Hallway Whiteboard by the Music Nook to reveal the invisible ink!',
      'DIGIT #3 = 2'
    );
  }
}

// Puzzle #4: UV Blacklight Whiteboard
function inspectWhiteboard() {
  if (lightMode === 'UV' || foundClues.has('whiteboard')) {
    markClueFound('whiteboard');
    playTone(740, 0.2, 'sine', 0.14);
    openInfoModal(
      'CLUE 4 OF 4 — UV BLACKLIGHT REVEAL',
      'Invisible Neon Ink on the Whiteboard!',
      'Under your purple UV Blacklight, a hidden handwritten line glows brightly across the bottom of the whiteboard: "YALE LOCK FINAL DIGIT = 9. Combine all 4 digits at the Front Entry Door!"',
      'DIGIT #4 = 9'
    );
  } else if (hasUVLens) {
    playTone(320, 0.14);
    showToast('You have the UV Lens! Press [U] to turn on UV Blacklight, then inspect the Whiteboard again!', 3800);
  } else {
    playTone(260, 0.14);
    openInfoModal(
      'HALLWAY WHITEBOARD',
      'Ordinary Notes... Plus Faint Invisible Ink',
      'Your regular apartment notes are here, but there is a glossy UV-ink smudge along the bottom edge. Check the 3D Printer in the Studio Office to print a UV Blacklight Lens!',
      ''
    );
  }
}

const CLUE_DEFS = {
  laptop: {
    pos: new THREE.Vector3(-1.15, 1.12, -7.02),
    radius: 1.55,
    prompt: 'Inspect Skyline Bistro Laptop',
    action: () => {
      playTone(540, 0.12);
      openInfoModal(
        'CLUE 1 HINT — BISTRO LAPTOP',
        'Skyline Telemetry Active',
        'A terminal window reads: "Signal locked on the downtown roof across the street. Use the BINOCULARS resting on the windowsill right beside you to read the rooftop beacon frequency!"',
        foundClues.has('laptop') ? 'DIGIT #1 = 4' : 'USE BINOCULARS →'
      );
    },
  },
  binoculars: {
    pos: new THREE.Vector3(-0.48, 0.72, -7.38),
    radius: 1.65,
    prompt: 'Look Through Windowsill Binoculars',
    action: () => {
      binocularsZoom = !binocularsZoom;
      camera.fov = binocularsZoom ? 22 : 68;
      camera.updateProjectionMatrix();
      binoOverlay.classList.toggle('hidden', !binocularsZoom);
      if (binocularsZoom) {
        playTone(640, 0.15);
        markClueFound('laptop');
        addInventory('Skyline Beacon #1');
      }
    },
  },
  music: {
    pos: new THREE.Vector3(1.82, 0.95, -1.45),
    radius: 1.80,
    prompt: 'Play MIDI Keyboard Synth Puzzle',
    action: () => openMidiModal(),
  },
  printer: {
    pos: new THREE.Vector3(-3.35, 1.15, 4.15),
    radius: 1.90,
    prompt: 'Operate Studio 3D Printer (Cyan Spool)',
    action: () => trigger3DPrinter(),
  },
  whiteboard: {
    pos: new THREE.Vector3(1.52, 1.50, -2.55),
    radius: 1.80,
    prompt: 'Inspect Hallway Whiteboard',
    action: () => inspectWhiteboard(),
  },
  coffee: {
    pos: new THREE.Vector3(-3.45, 1.10, -0.54),
    radius: 1.55,
    prompt: 'Brew Espresso (Speed Boost)',
    action: () => {
      caffeineUntil = performance.now() + 15000;
      [440, 554, 659].forEach((f, i) => setTimeout(() => playTone(f, 0.12), i * 80));
      showToast('Fresh Espresso! Sprint speed boosted for 15 seconds!', 2600);
    },
  },
  microwave: {
    pos: new THREE.Vector3(-2.22, 1.65, 1.55),
    radius: 1.70,
    prompt: 'Check Kitchen Microwave Display',
    action: () => {
      playTone(1040, 0.18, 'square', 0.08);
      showToast('Microwave LCD flashes: "Order of digits: Skyline → Music → Studio → Whiteboard"', 3800);
    },
  },
  keypad: {
    pos: new THREE.Vector3(4.05, 1.18, 2.65),
    radius: 1.80,
    prompt: 'Use Front Door Yale Smart Keypad',
    action: () => openKeypad(),
  },
};

const beacons = [];
Object.entries(CLUE_DEFS).forEach(([key, def]) => {
  const isMain = ['laptop', 'music', 'printer', 'whiteboard', 'keypad'].includes(key);
  const col = key === 'keypad' ? 0xff7b72 : (isMain ? 0x58d5ff : 0xf0c674);
  const m = new THREE.Mesh(
    new THREE.SphereGeometry(isMain ? 0.055 : 0.04, 14, 14),
    new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.78 })
  );
  m.position.copy(def.pos).add(new THREE.Vector3(0, 0.18, 0));
  scene.add(m);
  beacons.push({ key, mesh: m, baseY: m.position.y });
  interactables.push({ key, ...def });
});

// Keypad
let enteredPin = '';
function updateKeypadUI() {
  keypadDisplay.textContent = [0, 1, 2, 3].map((i) => enteredPin[i] || '_').join(' ');
}
function openKeypad() {
  enteredPin = '';
  updateKeypadUI();
  keypadMsg.style.color = '#9ab0c9';
  keypadMsg.textContent = foundClues.size === 4
    ? 'All 4 digits discovered! Enter the Yale PIN.'
    : `Digits found: ${foundClues.size}/4 — order: Skyline → Music → Studio → Whiteboard`;
  keypadModal.classList.remove('hidden');
  activeModal = keypadModal;
  controls.unlock();
}

document.querySelectorAll('.kp-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    const k = btn.dataset.k;
    if (k === 'C') {
      enteredPin = '';
      playTone(300, 0.08);
      updateKeypadUI();
    } else if (k === 'OK') {
      if (enteredPin === ESCAPE_PIN) {
        escaped = true;
        [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => setTimeout(() => playTone(f, 0.28, 'triangle', 0.16), i * 90));
        keypadMsg.textContent = 'ACCESS GRANTED! Front door unlocking...';
        keypadMsg.style.color = '#7ee787';
        for (const [obj, st] of doorStates.entries()) {
          if (obj.name.includes('Door_FrontEntry')) {
            st.locked = false;
            st.isOpen = true;
          }
        }
        setTimeout(() => {
          closeModals();
          showToast(`YOU ESCAPED in ${timerLabel.textContent}! Front Entry Door is now unlocked!`, 7000);
        }, 700);
      } else {
        playTone(170, 0.28, 'sawtooth', 0.14);
        keypadMsg.textContent = 'INCORRECT PIN — check all 4 rooms!';
        keypadMsg.style.color = '#ff7b72';
        enteredPin = '';
        updateKeypadUI();
      }
    } else if (enteredPin.length < 4) {
      enteredPin += k;
      playTone(620 + Number(k) * 35, 0.07);
      updateKeypadUI();
    }
  });
});

function closeModals() {
  clueModal.classList.add('hidden');
  midiModal.classList.add('hidden');
  keypadModal.classList.add('hidden');
  activeModal = null;
  controls.lock();
}
document.getElementById('modal-close').addEventListener('click', closeModals);
document.getElementById('midi-close').addEventListener('click', closeModals);
document.getElementById('keypad-close').addEventListener('click', closeModals);

// ---------------------------------------------------------------------------
// Load Upgraded Blender 5.3 GLB + Aligned COLMAP 3D Point Cloud Overlay
// ---------------------------------------------------------------------------
const loader = new GLTFLoader();
let scanPointCloud = null;
let scanVisible = false;

loader.load(
  '../exports/apartment_escape_room.glb',
  (gltf) => {
    const root = gltf.scene;
    root.traverse((child) => {
      if (child.isMesh) {
        child.castShadow = !child.name.includes('Skyline') && !child.name.includes('Glass');
        child.receiveShadow = true;
        if (child.name.includes('Glass')) {
          child.material.transparent = true;
          child.material.opacity = 0.15;
          child.material.depthWrite = false;
        }
      }
      if (child.name === 'Off_3DPrinter1_Head') printerHeadObj = child;
      if (child.name === 'Off_3DPrinter1_UVLensPrint') uvLensMesh = child;
      if (
        child.name.startsWith('Door_') &&
        !child.name.includes('_Handle') &&
        !child.name.includes('_SmartKeypad') &&
        !child.name.includes('_Frame') &&
        !child.name.includes('Louvered')
      ) {
        const closedY = child.rotation.y;
        const isFront = child.name.includes('FrontEntry');
        const isAlreadyOpen = Math.abs(closedY) > 0.2;
        doorStates.set(child, {
          closedAngle: isAlreadyOpen ? 0 : closedY,
          openAngle: isAlreadyOpen ? closedY : (isFront ? Math.PI * 0.48 : Math.PI * 0.44),
          isOpen: isAlreadyOpen,
          locked: isFront,
          label: child.name.replace('Door_', '').replace(/([A-Z])/g, ' $1').trim(),
        });
      }
    });
    scene.add(root);
    loadStatus.textContent = 'Ready! Upgraded Blender 5.3 apartment + real photo textures loaded.';
  },
  (xhr) => {
    if (xhr.total) loadStatus.textContent = `Loading apartment model: ${Math.round((xhr.loaded / xhr.total) * 100)}%`;
  },
  (err) => {
    console.error(err);
    loadStatus.textContent = 'Error loading GLB — serve project root via launch_walkthrough.bat.';
  }
);

fetch('../scan/living_scan_threejs.json')
  .then((r) => r.json())
  .then((data) => {
    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.Float32BufferAttribute(data.positions, 3));
    geom.setAttribute('color', new THREE.Float32BufferAttribute(data.colors, 3));
    scanPointCloud = new THREE.Points(
      geom,
      new THREE.PointsMaterial({ size: 0.055, vertexColors: true, transparent: true, opacity: 0.9 })
    );
    scanPointCloud.visible = scanVisible;
    scene.add(scanPointCloud);
  })
  .catch(() => {});

function toggleScanOverlay() {
  scanVisible = !scanVisible;
  if (scanPointCloud) scanPointCloud.visible = scanVisible;
  scanBadge.textContent = `3D Scan [P]: ${scanVisible ? 'ON' : 'OFF'}`;
  scanBadge.classList.toggle('on', scanVisible);
  showToast(scanVisible ? 'COLMAP 3D Video Scan Overlay: ON' : 'COLMAP 3D Video Scan Overlay: OFF', 1800);
}

// Wall Colliders
const COLLIDERS = [
  [-4.3, -3.82, -7.8, 6.2],
  [-4.2, 2.0, -7.85, -7.45],
  [1.56, 2.0, -7.65, -3.92],
  [1.56, 2.0, -3.05, -2.02],
  [2.26, 2.6, -2.08, -0.10],
  [1.56, 2.0, -0.15, 2.08],
  [1.58, 4.3, 1.92, 2.12],
  [4.12, 4.4, 1.92, 6.2],
  [1.20, 4.3, 5.92, 6.2],
  [-4.2, -0.25, 5.92, 6.2],
  [-4.2, -0.25, 1.96, 2.18],
  [-0.42, -0.22, 3.16, 6.1],
  [-0.42, 2.04, 3.82, 4.02],
  [2.86, 4.3, 3.82, 4.02],
  [1.16, 1.38, 3.84, 6.1],
  [-3.84, -0.72, -0.92, -0.04],
  [-3.84, -3.10, -0.80, 2.00],
  [-3.20, -0.35, 1.24, 2.02],
];

function resolveCollision(pos) {
  for (const [x0, x1, z0, z1] of COLLIDERS) {
    const cx = Math.max(x0, Math.min(pos.x, x1));
    const cz = Math.max(z0, Math.min(pos.z, z1));
    const dx = pos.x - cx;
    const dz = pos.z - cz;
    const distSq = dx * dx + dz * dz;
    if (distSq < PLAYER_RADIUS * PLAYER_RADIUS) {
      const dist = Math.sqrt(distSq) || 0.0001;
      const push = PLAYER_RADIUS - dist;
      pos.x += (dx / dist) * push;
      pos.z += (dz / dist) * push;
    }
  }
}

function getRoomName(x, z) {
  const by = -z;
  if (by > 2.7) return 'Corner Living Room';
  if (by > 0.8 && x > 0.9) return 'Music Production Nook';
  if (by > 0.8) return 'Dining Area';
  if (by > -2.0 && x < 0.0) return 'Kitchen';
  if (x < -0.3 && by <= -2.0) return 'Studio / 3D Printer Office';
  if (x > 1.25 && by < -3.85) return 'Bathroom';
  return 'Entry Hallway';
}

const TELEPORTS = {
  Digit1: { pos: [-0.6, EYE_HEIGHT, -4.0], look: [-2.0, 1.3, -6.5], name: 'Living Room' },
  Digit2: { pos: [0.3, EYE_HEIGHT, -0.9], look: [-2.2, 1.1, 0.8], name: 'Kitchen & Music Nook' },
  Digit3: { pos: [-1.3, EYE_HEIGHT, 3.2], look: [-3.3, 1.1, 4.3], name: 'Studio Office' },
  Digit4: { pos: [2.4, EYE_HEIGHT, 2.9], look: [4.1, 1.2, 2.9], name: 'Front Entryway' },
};

document.getElementById('btn-play').addEventListener('click', () => controls.lock());

controls.addEventListener('lock', () => {
  overlay.classList.add('hidden');
  hud.classList.remove('hidden');
  if (!startTime) startTime = performance.now();
});
controls.addEventListener('unlock', () => {
  if (binocularsZoom) {
    binocularsZoom = false;
    camera.fov = 68;
    camera.updateProjectionMatrix();
    binoOverlay.classList.add('hidden');
  }
  if (!activeModal) overlay.classList.remove('hidden');
});

window.addEventListener('keydown', (e) => {
  keys[e.code] = true;
  if (activeModal && e.code === 'Escape') {
    closeModals();
    return;
  }
  if (!controls.isLocked) return;

  if (e.code === 'KeyP') toggleScanOverlay();
  if (e.code === 'KeyF') setLightMode(lightMode === 'WHITE' ? 'OFF' : 'WHITE');
  if (e.code === 'KeyU') {
    if (!hasUVLens) showToast('No UV Lens yet! Check the 3D Printer in the Studio Office.', 2600);
    else setLightMode(lightMode === 'UV' ? 'OFF' : 'UV');
  }
  if (e.code === 'KeyE') {
    if (binocularsZoom) {
      binocularsZoom = false;
      camera.fov = 68;
      camera.updateProjectionMatrix();
      binoOverlay.classList.add('hidden');
      return;
    }
    tryInteract();
  }
  if (TELEPORTS[e.code]) {
    const t = TELEPORTS[e.code];
    camera.position.set(...t.pos);
    camera.lookAt(...t.look);
    showToast(`Teleported to ${t.name}`, 1600);
  }
});
window.addEventListener('keyup', (e) => { keys[e.code] = false; });

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

function findNearestInteraction() {
  const p = camera.position;
  let best = null;
  let bestDist = Infinity;
  for (const item of interactables) {
    const d = p.distanceTo(item.pos);
    if (d < item.radius && d < bestDist) {
      best = { type: 'clue', item };
      bestDist = d;
    }
  }
  const doorWorld = new THREE.Vector3();
  for (const [obj, st] of doorStates.entries()) {
    obj.getWorldPosition(doorWorld);
    const d = p.distanceTo(doorWorld);
    if (d < 1.65 && d < bestDist) {
      best = { type: 'door', obj, st };
      bestDist = d;
    }
  }
  return best;
}

function tryInteract() {
  const hit = findNearestInteraction();
  if (!hit) return;
  if (hit.type === 'clue') {
    hit.item.action();
  } else if (hit.type === 'door') {
    if (hit.st.locked) openKeypad();
    else {
      hit.st.isOpen = !hit.st.isOpen;
      playTone(hit.st.isOpen ? 360 : 280, 0.1);
      showToast(`${hit.st.label}: ${hit.st.isOpen ? 'Opened' : 'Closed'}`, 1400);
    }
  }
}

// Top-Down Live Minimap
const mm = document.getElementById('minimap');
const mctx = mm.getContext('2d');
function drawMinimap() {
  mctx.clearRect(0, 0, mm.width, mm.height);
  const toMX = (x) => ((x + 4.4) / 9.0) * (mm.width - 16) + 8;
  const toMY = (z) => ((z + 7.8) / 14.2) * (mm.height - 16) + 8;

  const drawRect = (x0, x1, by0, by1, fill) => {
    mctx.fillStyle = fill;
    const rx0 = toMX(x0), rx1 = toMX(x1);
    const ry0 = toMY(-by1), ry1 = toMY(-by0);
    mctx.fillRect(rx0, ry0, rx1 - rx0, ry1 - ry0);
    mctx.strokeStyle = 'rgba(255,255,255,0.22)';
    mctx.strokeRect(rx0, ry0, rx1 - rx0, ry1 - ry0);
  };
  drawRect(-3.9, 1.65, -2.0, 7.55, 'rgba(88, 166, 255, 0.14)');
  drawRect(-4.0, -0.32, -6.0, -2.05, 'rgba(163, 113, 247, 0.16)');
  drawRect(-0.32, 4.2, -3.9, -2.0, 'rgba(210, 153, 34, 0.14)');
  drawRect(1.25, 4.2, -6.0, -3.9, 'rgba(63, 185, 80, 0.14)');

  for (const b of beacons) {
    mctx.fillStyle = foundClues.has(b.key) ? '#7ee787' : (b.key === 'keypad' ? '#ff7b72' : '#58d5ff');
    mctx.beginPath();
    mctx.arc(toMX(b.mesh.position.x), toMY(b.mesh.position.z), 3.1, 0, Math.PI * 2);
    mctx.fill();
  }

  const px = toMX(camera.position.x);
  const py = toMY(camera.position.z);
  const dir = new THREE.Vector3();
  camera.getWorldDirection(dir);
  const ang = Math.atan2(dir.z, dir.x);
  mctx.fillStyle = 'rgba(255, 220, 90, 0.35)';
  mctx.beginPath();
  mctx.moveTo(px, py);
  mctx.arc(px, py, 16, ang - 0.45, ang + 0.45);
  mctx.closePath();
  mctx.fill();

  mctx.fillStyle = '#ffdf5d';
  mctx.beginPath();
  mctx.arc(px, py, 4, 0, Math.PI * 2);
  mctx.fill();
}

const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.05);
  const t = clock.elapsedTime;

  for (const b of beacons) {
    b.mesh.position.y = b.baseY + Math.sin(t * 2.8 + b.baseY) * 0.032;
  }

  // Animate 3D printer head when printing!
  if (printerHeadObj && performance.now() < printerAnimatingUntil) {
    printerHeadObj.position.z = 4.15 + Math.sin(t * 24) * 0.13;
  }

  for (const [obj, st] of doorStates.entries()) {
    const target = st.isOpen ? st.openAngle : st.closedAngle;
    obj.rotation.y += (target - obj.rotation.y) * Math.min(1, dt * 7);
  }

  if (controls.isLocked) {
    const boost = performance.now() < caffeineUntil ? 1.38 : 1.0;
    const speed = ((keys['ShiftLeft'] || keys['ShiftRight']) ? 4.4 : 2.6) * boost;
    let fwd = 0, right = 0;
    if (keys['KeyW'] || keys['ArrowUp']) fwd += 1;
    if (keys['KeyS'] || keys['ArrowDown']) fwd -= 1;
    if (keys['KeyD'] || keys['ArrowRight']) right += 1;
    if (keys['KeyA'] || keys['ArrowLeft']) right -= 1;

    if (fwd !== 0 || right !== 0) {
      const len = Math.hypot(fwd, right);
      controls.moveForward((fwd / len) * speed * dt);
      controls.moveRight((right / len) * speed * dt);
      camera.position.y = EYE_HEIGHT;
      resolveCollision(camera.position);
    }

    roomLabel.textContent = getRoomName(camera.position.x, camera.position.z);

    if (startTime && !escaped) {
      const secs = Math.floor((performance.now() - startTime) / 1000);
      timerLabel.textContent = `${String(Math.floor(secs / 60)).padStart(2, '0')}:${String(secs % 60).padStart(2, '0')}`;
    }

    const hit = findNearestInteraction();
    if (hit && !binocularsZoom) {
      reticle.classList.add('active');
      interactPrompt.classList.remove('hidden');
      if (hit.type === 'clue') {
        interactPrompt.innerHTML = `Press <kbd>E</kbd> — ${hit.item.prompt}`;
      } else {
        const verb = hit.st.locked ? 'Unlock (Keypad)' : (hit.st.isOpen ? 'Close' : 'Open');
        interactPrompt.innerHTML = `Press <kbd>E</kbd> — ${verb} ${hit.st.label}`;
      }
    } else {
      reticle.classList.remove('active');
      interactPrompt.classList.add('hidden');
    }

    drawMinimap();
  }

  renderer.render(scene, camera);
}
animate();
