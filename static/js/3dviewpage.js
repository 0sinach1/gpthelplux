import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import { EXRLoader } from 'three/examples/jsm/loaders/EXRLoader.js';
import { PMREMGenerator } from 'three';

const scene = new THREE.Scene();
const loader = new GLTFLoader();

const clock = new THREE.Clock();
let mixer = null;

// DRACO loader setup
const dracoLoader = new DRACOLoader();

// IMPORTANT: Your decoder files must be inside this folder:
dracoLoader.setDecoderPath('/static/draco/');  // <-- adjust to your file location

loader.setDRACOLoader(dracoLoader);

const canvas = document.getElementById('d3view');
const renderer = new THREE.WebGLRenderer({ canvas, alpha: true });
renderer.setSize(canvas.clientWidth, canvas.clientHeight);

const camera = new THREE.PerspectiveCamera(
    75, canvas.clientWidth / canvas.clientHeight, 0.001, 2000
);

camera.position.z = 2;

const controls = new OrbitControls(camera, renderer.domElement);

controls.enableDamping = true; // smooth motion
controls.dampingFactor = 0.05;

controls.enableZoom = true;   // mouse wheel zoom
controls.enablePan = true;    // right-click or two-finger pan
controls.autoRotate = false;  // optional: rotate automatically
controls.minDistance = 0.1;
controls.maxDistance = 25;

controls.screenSpacePanning = false; // optional, see below

const pmremGenerator = new PMREMGenerator(renderer);
pmremGenerator.compileEquirectangularShader();

var model;
let modelLink = '/static/products3d/topeBrownClassics.glb';
var animationornot = document.getElementById('animationornot');

// Get 3D model URL from data attribute or use default
const modelUrl = canvas ? (canvas.dataset.modelUrl || modelLink) : modelLink;

// color dot elements
const colorDots = document.querySelectorAll('.color-dot');

// loading element
const loadingScreen = document.getElementById('viewer-loading');
let assetsToLoad = 2; // 1 = 3D model, 1 = HDRI environment

function checkLoadingDone() {
    assetsToLoad--;
    if (assetsToLoad <= 0 && loadingScreen) {
        loadingScreen.style.display = 'none';
    }
}

let targetMesh = null;
window.currentModel = null;

let isRotating = true

loader.load(modelUrl, gltf => {
    model = gltf.scene;
    model.scale.set(1, 1, 1);  // adjust to fit your scene
    model.position.set(0, 0, 0);
    scene.add(model);

    window.currentModel = model;

    // Check if the loaded model has animations
    if (gltf.animations && gltf.animations.length > 0) {
        mixer = new THREE.AnimationMixer(model);
        
        // Load the animations but don't advance time yet
        gltf.animations.forEach((clip) => {
            mixer.clipAction(clip).play();
        });

        // 1. STOP ON LOAD: Set speed to 0 immediately
        mixer.timeScale = 0;

        // 2. BUTTON SETUP: Show only Play button, hide Pause
        const btnPlay = document.getElementById('animPlay');
        const btnPause = document.getElementById('animPause');

        // Show or hide animationornot text
        animationornot.style.display = 'flex';
        
        if(btnPlay) btnPlay.style.display = 'inline-block';
        if(btnPause) btnPause.style.display = 'none';
    }

    checkLoadingDone()

    // autodetect first mesh as targetMesh
    model.traverse(child => {
        if (child.isMesh && !targetMesh) targetMesh = child;
    });

    let isRotationPaused = false;
    let rotationTimeout;

    controls.target.set(0, 0, 0);

    // Optional: rotate or animate
    function animateModel() {
        requestAnimationFrame(animateModel);

        if (isRotating && model) {
            model.rotation.y += 0.005; // adjust speed as needed
        }

        // Update the animation mixer if it exists
        if (mixer) {
            const delta = clock.getDelta();
            mixer.update(delta);
        }

        controls.update();  // required when using damping
        renderer.render(scene, camera);
    }

    animateModel();

    function pauseRotation() {
        isRotationPaused = true;
        clearTimeout(rotationTimeout); // reset timer if user keeps clicking
        rotationTimeout = setTimeout(() => {
            isRotationPaused = false;
        }, 1000000000); // never resume
    }

    function holdButton(btnId, onHold) {
        let interval;
        const btn = document.getElementById(btnId);

        btn.addEventListener('mousedown', () => {
            onHold(); // immediate action
            interval = setInterval(onHold, 50); // keep repeating while held
            pauseRotation(); // also pause rotation
        });

        btn.addEventListener('mouseup', () => clearInterval(interval));
        btn.addEventListener('mouseleave', () => clearInterval(interval));
    }

    function zoomByScale(scale) {
        // direction from target to camera
        const dir = new THREE.Vector3();
        dir.copy(camera.position).sub(controls.target).normalize();

        // current distance
        const distance = camera.position.distanceTo(controls.target);

        // new distance (apply scale)
        const newDistance = THREE.MathUtils.clamp(distance * scale, controls.minDistance, controls.maxDistance);

        // set camera position: target + dir * newDistance
        camera.position.copy(controls.target).addScaledVector(dir, newDistance);
    }

    // onhold buttons
    holdButton('zoomIn', () => zoomByScale(1.03));
    holdButton('zoomOut', () => zoomByScale(0.97));
    holdButton('rotateLeft', () => model.rotation.y -= 0.08);
    holdButton('rotateRight', () => model.rotation.y += 0.08);

    // Camera position presets (pan to viewpoints)
    function setView(x, y, z) {
        camera.position.set(x, y, z);
        controls.target.set(0, 0, 0); // center of model
        pauseRotation();
    }

    // Animation Play/Pause Logic
    const btnPlay = document.getElementById('animPlay');
    const btnPause = document.getElementById('animPause');

    if (btnPlay) {
        btnPlay.addEventListener('click', () => {
            if (mixer) mixer.timeScale = 1; // Start animation
            
            // Toggle visibility: Hide Play, Show Pause
            btnPlay.style.display = 'none';
            btnPause.style.display = 'inline-block';
        });
    }

    if (btnPause) {
        btnPause.addEventListener('click', () => {
            if (mixer) mixer.timeScale = 0; // Freeze animation
            
            // Toggle visibility: Hide Pause, Show Play
            btnPause.style.display = 'none';
            btnPlay.style.display = 'inline-block';
        });
    }

    document.getElementById('view1').addEventListener('click', () => setView(0, 0, 4));
    document.getElementById('view2').addEventListener('click', () => setView(4, 0, 0));
    document.getElementById('view3').addEventListener('click', () => setView(0, 4, 0));
    document.getElementById('view4').addEventListener('click', () => setView(3, 3, 3));

},
xhr => {
    // called while loading
    if (xhr.lengthComputable) {
        const percent = (xhr.loaded / xhr.total) * 100;
    }
},
 undefined, error => {
    console.error(error);
    checkLoadingDone();
});

// Adding color change functionality to targetMesh of model

function applyColorToMesh(meshName, hex) {
    if (!window.currentModel) return;

    const color = new THREE.Color(hex);

    window.currentModel.traverse(child => {
        if (child.isMesh && child.material && child.name === meshName) {
            if (Array.isArray(child.material)) {
                child.material.forEach(m => {
                    if (m.color) m.color.set(color);
                });
            } else if (child.material.color) {
                child.material.color.set(color);
            }
        }
    });
}

colorDots.forEach(dot => {
    dot.addEventListener('click', () => {
        // Remove 'selected' from all dots in this mesh
        const parentMeshName = dot.dataset.mesh;
        colorDots.forEach(d => {
            if (d.dataset.mesh === parentMeshName) d.classList.remove('selected');
        });

        // Add 'selected' to clicked one
        dot.classList.add('selected');

        if (!targetMesh) return;

        const hex = dot.style.backgroundColor;
        const meshName = dot.dataset.mesh;

        applyColorToMesh(meshName, hex);
    });
});

// --- TEXTURE SWAPPING LOGIC ---

const textureLoader = new THREE.TextureLoader();
const textureBtns = document.querySelectorAll('.texture-btn');

// Store the original map to restore it later
let originalMap = null;

function applyTexture(url) {
    if (!window.currentModel) return;

    // Load the new texture
    textureLoader.load(url, (texture) => {
        // IMPORTANT: GLTF models usually require flipY to be false
        texture.flipY = false; 
        texture.colorSpace = THREE.SRGBColorSpace; // Modern Three.js color correction

        window.currentModel.traverse((child) => {
            if (child.isMesh && child.material) {
                // Save original map if we haven't yet
                if (!originalMap && child.material.map) {
                    originalMap = child.material.map;
                }

                // Apply new texture
                child.material.map = texture;
                child.material.needsUpdate = true;
            }
        });
    });
}

function resetTexture() {
    if (!window.currentModel || !originalMap) return;

    window.currentModel.traverse((child) => {
        if (child.isMesh && child.material) {
            child.material.map = originalMap;
            child.material.needsUpdate = true;
        }
    });
}

// Event Listeners for Buttons
textureBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        // UI Selection State
        textureBtns.forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');

        const url = btn.dataset.textureUrl;
        
        if (url) {
            applyTexture(url); // Load and apply new texture
        } else {
            resetTexture(); // Revert to original GLB texture
        }
    });
});

// Creating the hdri environment
const exrLoader = new EXRLoader();
exrLoader.load("https://luxa-media.s3.eu-north-1.amazonaws.com/static/environments3d/studio_small_08_2k.exr", texture => {
    texture.mapping = THREE.EquirectangularReflectionMapping;

    const envMap = pmremGenerator.fromEquirectangular(texture).texture;
    scene.environment = envMap;   // apply to the scene

    texture.dispose();
    pmremGenerator.dispose();

    checkLoadingDone();
},
    undefined,
    err => {
        console.error(err);
        checkLoadingDone();
    }
);


const ambience = new THREE.AmbientLight(0xffffff, 0.5);
scene.add(ambience);

function onWindowResize() {
    camera.aspect = canvas.clientWidth / canvas.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(canvas.clientWidth, canvas.clientHeight);
}

// Detect double tap manually (because mobile browsers don't fire dblclick)
let lastTap = 0;

const modelcont = document.getElementsByClassName("pro3dview")[0]

function toggleRotation() {
    isRotating = !isRotating;

    const msg = document.createElement("div");
    msg.textContent = isRotating ? "Rotation ON" : "Rotation OFF";
    msg.style.position = "absolute";
    msg.style.top = "20px";
    msg.style.left = "50%";
    msg.style.transform = "translateX(-50%)";
    msg.style.background = "rgba(0,0,0,0.6)";
    msg.style.color = "white";
    msg.style.padding = "6px 14px";
    msg.style.borderRadius = "6px";
    msg.style.zIndex = 9999;

    modelcont.appendChild(msg);
    setTimeout(() => msg.remove(), 1500);
}

// Desktop double-click
renderer.domElement.addEventListener("dblclick", toggleRotation);

// --- IMPROVED MOBILE DOUBLE TAP ---
let lastTapTime = 0;
let touchStartX = 0;
let touchStartY = 0;
let isDragging = false;

// 1. TOUCH START: Record position & reset drag flag
renderer.domElement.addEventListener("touchstart", function (e) {
    if (e.touches.length > 1) return; // Ignore pinch/zoom gestures

    const touch = e.touches[0];
    touchStartX = touch.clientX;
    touchStartY = touch.clientY;
    isDragging = false; 
}, { passive: true });

// 2. TOUCH MOVE: Detect if user is dragging/rotating
renderer.domElement.addEventListener("touchmove", function (e) {
    if (isDragging) return; // Already marked as drag

    const touch = e.touches[0];
    const moveX = Math.abs(touch.clientX - touchStartX);
    const moveY = Math.abs(touch.clientY - touchStartY);

    // If finger moves more than 10px, it's a Rotate/Pan action, NOT a tap
    if (moveX > 10 || moveY > 10) {
        isDragging = true;
    }
}, { passive: true });

// 3. TOUCH END: Trigger only if it was a clean tap (no drag)
renderer.domElement.addEventListener("touchend", function (e) {
    // If user was rotating the model, ignore this event
    if (isDragging) return;

    const currentTime = new Date().getTime();
    const tapLength = currentTime - lastTapTime;

    // Standard Double Tap Check ( < 300ms )
    if (tapLength < 300 && tapLength > 0) {
        if (e.cancelable) e.preventDefault(); // Stop browser zoom
        toggleRotation();
        lastTapTime = 0; // Reset to prevent triple-tap triggering
    } else {
        lastTapTime = currentTime; // Mark this as the first tap
    }
});

window.addEventListener('resize', onWindowResize, false);
