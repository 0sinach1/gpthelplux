import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { EXRLoader } from 'three/examples/jsm/loaders/EXRLoader.js';
import { PMREMGenerator } from 'three';

const scene = new THREE.Scene();
const loader = new GLTFLoader();

const canvas = document.getElementById('d3view');
const renderer = new THREE.WebGLRenderer({ canvas, alpha: true });
renderer.setSize(canvas.clientWidth, canvas.clientHeight);

const camera = new THREE.PerspectiveCamera(
    75, canvas.clientWidth / canvas.clientHeight, 0.01, 2000
);

camera.position.z = 4;

const controls = new OrbitControls(camera, renderer.domElement);

controls.enableDamping = true; // smooth motion
controls.dampingFactor = 0.05;

controls.enableZoom = true;   // mouse wheel zoom
controls.enablePan = true;    // right-click or two-finger pan
controls.autoRotate = false;  // optional: rotate automatically
controls.minDistance = 0.05;
controls.maxDistance = 25;

controls.screenSpacePanning = false; // optional, see below

const pmremGenerator = new PMREMGenerator(renderer);
pmremGenerator.compileEquirectangularShader();

var model;
let modelLink = '/static/products3d/topeBrownClassics.glb';

// Get 3D model URL from data attribute or use default
const modelUrl = canvas ? (canvas.dataset.modelUrl || modelLink) : modelLink;

loader.load(modelUrl, gltf => {
    model = gltf.scene;
    model.scale.set(1, 1, 1);  // adjust to fit your scene
    model.position.set(0, 0, 0);
    scene.add(model);

    let isRotationPaused = false;
    let rotationTimeout;

    controls.target.set(0, 0, 0);

    // Optional: rotate or animate
    function animateModel() {
        requestAnimationFrame(animateModel);

        if (!isRotationPaused) {
            model.rotation.y += 0.002;
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
        }, 10000); // resume after 10s
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

    document.getElementById('view1').addEventListener('click', () => setView(0, 0, 4));
    document.getElementById('view2').addEventListener('click', () => setView(4, 0, 0));
    document.getElementById('view3').addEventListener('click', () => setView(0, 4, 0));
    document.getElementById('view4').addEventListener('click', () => setView(3, 3, 3));

}, undefined, error => {
    console.error(error);
});

// Adding color change functionality to targetMesh (necklace only) of shoemodel

const colorDots = document.querySelectorAll('.color-dot');

colorDots.forEach(dot => {
    dot.addEventListener('click', () => {
        // Remove 'selected' from all
        colorDots.forEach(d => d.classList.remove('selected'));

        // Add 'selected' to clicked one
        dot.classList.add('selected');

        if (!targetMesh) return;

        const colorHex = new THREE.Color(dot.style.background).getHex();

        window.currentModel.traverse(child => {
            if (child.isMesh && child.material) {
                if (Array.isArray(child.material)) {
                    child.material.forEach(mat => {
                        if (mat.color) mat.color.set(colorHex);
                    });
                } else if (child.material.color) {
                    child.material.color.set(colorHex);
                }
            }
        });

        if (Array.isArray(targetMesh.material)) {
            targetMesh.material.forEach(mat => { if(mat.color) mat.color.set(colorHex); });
        } else if (targetMesh.material.color) {
            targetMesh.material.color.set(colorHex);
        }
    });
});

// Creating the hdri environment
const exrLoader = new EXRLoader();
exrLoader.load('/static/environments3d/studio_small_08_4k.exr', texture => {
    const envMap = pmremGenerator.fromEquirectangular(texture).texture;
    scene.environment = envMap;   // apply to the scene
    texture.dispose();
    pmremGenerator.dispose();
});

const ambience = new THREE.AmbientLight(0xffffff, 0.5);
scene.add(ambience);

function onWindowResize() {
    camera.aspect = canvas.clientWidth / canvas.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(canvas.clientWidth, canvas.clientHeight);
}

window.addEventListener('resize', onWindowResize, false);


// Adding hover effect for information on 3d model viewer [IN CSS NW]
var infobtn = document.getElementById("infobtn")
var info = document.getElementById("info")
