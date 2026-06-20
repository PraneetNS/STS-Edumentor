// BirdAvatar.js
// Procedural blue bird mascot for EduMentor — vanilla Three.js, no external models.
//
// Usage in your existing app:
//   import * as THREE from 'three';
//   import { createBirdAvatar } from './BirdAvatar.js';
//
//   const bird = createBirdAvatar(THREE);
//   scene.add(bird.group);
//
//   // in your render loop (time = seconds, delta = seconds since last frame):
//   bird.update(time, delta);
//
//   // drive it from your app state:
//   bird.setState('idle' | 'listening' | 'speaking' | 'thinking');
//   bird.setAmplitude(0.0–1.0); // mic/TTS amplitude, used only in 'speaking'

export function createBirdAvatar(THREE, opts = {}) {
  const palette = Object.assign(
    {
      body: '#3D6FF2', // primary cobalt blue
      bodyDark: '#2A52C9', // wings / shading
      bodyLight: '#7FA8FF', // crown highlight
      belly: '#D7E6FF', // pale belly patch
      beak: '#FFB648', // warm accent (upper)
      beakDark: '#E8983A', // warm accent (lower, contrast)
      eyeWhite: '#FFFFFF',
      pupil: '#1A1E3A',
    },
    opts.palette || {}
  );

  const group = new THREE.Group();
  group.name = 'EduMentorBird';

  // ---------------- materials ----------------
  const matBody = new THREE.MeshStandardMaterial({ color: palette.body, roughness: 0.45, metalness: 0.05 });
  const matBodyDark = new THREE.MeshStandardMaterial({ color: palette.bodyDark, roughness: 0.5, metalness: 0.05 });
  const matBodyLight = new THREE.MeshStandardMaterial({
    color: palette.bodyLight,
    roughness: 0.4,
    metalness: 0.05,
    transparent: true,
    opacity: 0.55,
  });
  const matBelly = new THREE.MeshStandardMaterial({ color: palette.belly, roughness: 0.5 });
  const matBeak = new THREE.MeshStandardMaterial({ color: palette.beak, roughness: 0.35, metalness: 0.1 });
  const matBeakDark = new THREE.MeshStandardMaterial({ color: palette.beakDark, roughness: 0.35, metalness: 0.1 });
  const matEyeWhite = new THREE.MeshStandardMaterial({ color: palette.eyeWhite, roughness: 0.2 });
  const matPupil = new THREE.MeshStandardMaterial({ color: palette.pupil, roughness: 0.1 });

  // ---------------- body ----------------
  const bodyGroup = new THREE.Group();
  group.add(bodyGroup);

  const body = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 48), matBody);
  body.scale.set(1, 1.18, 0.92);
  bodyGroup.add(body);

  // soft lighter crown highlight (top-back cap), gives the "shaded sphere" look
  const crown = new THREE.Mesh(
    new THREE.SphereGeometry(1.01, 32, 32, 0, Math.PI * 2, 0, Math.PI * 0.45),
    matBodyLight
  );
  crown.scale.set(1, 1.18, 0.92);
  crown.position.y = 0.05;
  bodyGroup.add(crown);

  // pale belly patch
  const belly = new THREE.Mesh(new THREE.SphereGeometry(0.62, 32, 32), matBelly);
  belly.scale.set(1, 1.15, 0.55);
  belly.position.set(0, -0.32, 0.62);
  bodyGroup.add(belly);

  // tail
  const tail = new THREE.Mesh(new THREE.ConeGeometry(0.28, 0.6, 16), matBodyDark);
  tail.rotation.x = Math.PI / 2.1;
  tail.position.set(0, 0.05, -0.95);
  bodyGroup.add(tail);

  // ---------------- eyes ----------------
  const eyeGroup = new THREE.Group();
  eyeGroup.position.set(0, 0.28, 0.78);
  bodyGroup.add(eyeGroup);

  function makeEye(side) {
    const e = new THREE.Group();
    const white = new THREE.Mesh(new THREE.SphereGeometry(0.26, 24, 24), matEyeWhite);
    white.scale.set(1, 1.15, 0.7);
    e.add(white);
    const pupil = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 16), matPupil);
    pupil.position.set(0, -0.02, 0.18);
    pupil.name = 'pupil';
    e.add(pupil);
    const shine = new THREE.Mesh(new THREE.SphereGeometry(0.04, 8, 8), matEyeWhite);
    shine.position.set(0.05, 0.08, 0.27);
    e.add(shine);
    e.position.set(side * 0.34, 0, 0);
    e.name = 'eye-' + (side > 0 ? 'r' : 'l');
    return e;
  }
  const eyeL = makeEye(-1);
  const eyeR = makeEye(1);
  eyeGroup.add(eyeL, eyeR);

  // ---------------- beak (split upper/lower for mouth-sync) ----------------
  const beakGroup = new THREE.Group();
  beakGroup.position.set(0, 0.1, 0.95);
  bodyGroup.add(beakGroup);

  const beakUpper = new THREE.Mesh(new THREE.ConeGeometry(0.22, 0.42, 16), matBeak);
  beakUpper.rotation.x = Math.PI / 2;
  beakUpper.position.set(0, 0.03, 0.18);
  beakGroup.add(beakUpper);

  const lowerPivot = new THREE.Group();
  lowerPivot.position.set(0, -0.02, 0.05);
  beakGroup.add(lowerPivot);
  const beakLower = new THREE.Mesh(new THREE.ConeGeometry(0.18, 0.3, 16), matBeakDark);
  beakLower.rotation.x = Math.PI / 2;
  beakLower.position.set(0, -0.05, 0.16);
  lowerPivot.add(beakLower);

  // ---------------- wings (pivot at shoulder so they can swing up to the head) ----------------
  function makeWing(side) {
    const pivot = new THREE.Group();
    pivot.position.set(side * 0.95, -0.1, 0.05);
    const wing = new THREE.Mesh(new THREE.SphereGeometry(0.5, 20, 20), matBodyDark);
    wing.scale.set(0.32, 0.85, 0.18);
    wing.position.set(side * 0.18, -0.15, 0);
    pivot.add(wing);
    // rest = relaxed at sides, up = lifted toward head ("listening" ear-cup pose)
    pivot.userData.restZ = side * -0.35;
    pivot.userData.upZ = side * -2.05;
    pivot.userData.restX = 0.1;
    pivot.userData.upX = -0.5;
    pivot.rotation.z = pivot.userData.restZ;
    pivot.rotation.x = pivot.userData.restX;
    return pivot;
  }
  const wingL = makeWing(-1);
  const wingR = makeWing(1);
  bodyGroup.add(wingL, wingR);

  // ---------------- feet ----------------
  function makeFoot(side) {
    const f = new THREE.Mesh(new THREE.SphereGeometry(0.14, 12, 12), matBeak);
    f.scale.set(1, 0.5, 1.3);
    f.position.set(side * 0.32, -1.18, 0.15);
    return f;
  }
  bodyGroup.add(makeFoot(-1), makeFoot(1));

  // ================= state machine =================
  // wingLift: 0 (down) -> 1 (raised to ears)
  // hop: 0 (gentle idle bob) -> 1 (energetic hop bounce)
  // lean: forward/back body tilt
  // eyeScale: alertness
  // tilt: head-tilt + glance amount (used for 'thinking')
  // blinkRate: relative blink frequency multiplier
  const STATES = {
    idle: { wingLift: 0, hop: 0, lean: 0, eyeScale: 1.0, tilt: 0, blinkRate: 1.0 },
    listening: { wingLift: 1, hop: 1, lean: -0.16, eyeScale: 1.18, tilt: 0, blinkRate: 0.3 },
    speaking: { wingLift: 0.12, hop: 0.25, lean: 0.06, eyeScale: 1.0, tilt: 0, blinkRate: 0.6 },
    thinking: { wingLift: 0.08, hop: 0.15, lean: 0, eyeScale: 0.92, tilt: 1, blinkRate: 1.4 },
  };

  let current = Object.assign({}, STATES.idle);
  let target = STATES.idle;
  let stateName = 'idle';
  let amplitude = 0; // 0..1, set externally during 'speaking'

  let blinking = false;
  let blinkT = 0;
  let nextBlinkIn = 1 + Math.random() * 2;

  const baseY = 0;

  function setState(name) {
    if (!STATES[name] || name === stateName) {
      if (STATES[name]) target = STATES[name];
      return;
    }
    stateName = name;
    target = STATES[name];
  }

  function setAmplitude(v) {
    amplitude = Math.max(0, Math.min(1, v));
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function update(time, delta) {
    delta = Math.min(delta || 0.016, 0.05);
    const k = 1 - Math.pow(0.0005, delta); // smooth, ~frame-rate independent ease

    current.wingLift = lerp(current.wingLift, target.wingLift, k);
    current.hop = lerp(current.hop, target.hop, k);
    current.lean = lerp(current.lean, target.lean, k);
    current.eyeScale = lerp(current.eyeScale, target.eyeScale, k);
    current.tilt = lerp(current.tilt, target.tilt, k);

    // ---- vertical motion: blend gentle sine bob (idle) with a hop arc (listening) ----
    const sineBob = Math.sin(time * 1.3) * 0.045;
    const hopCycle = (time * 6.2) % (Math.PI * 2);
    const hopHeight = Math.abs(Math.sin(hopCycle)); // 0 at ground, 1 at peak
    const yOff = lerp(sineBob, hopHeight * 0.16, current.hop);
    bodyGroup.position.y = baseY + yOff;

    // cartoon squash (landing) / stretch (peak), only kicks in as hop blends in
    const stretch = lerp(0, hopHeight * 0.06, current.hop);
    const squash = lerp(0, (1 - hopHeight) * 0.05, current.hop);
    bodyGroup.scale.y = 1 + stretch - squash;
    bodyGroup.scale.x = bodyGroup.scale.z = 1 - stretch * 0.4 + squash * 0.4;

    // lean forward (listening, attentive) / back
    bodyGroup.rotation.x = current.lean;

    // idle head sway vs. deliberate side-tilt while thinking
    const idleSway = Math.sin(time * 0.45) * 0.05 * (1 - current.tilt);
    const thinkTilt = Math.sin(time * 0.7) * 0.18 * current.tilt;
    bodyGroup.rotation.z = idleSway + thinkTilt;

    // ---- wings: rest -> raised to "ears", with a flutter while listening ----
    [wingL, wingR].forEach((w) => {
      w.rotation.z = lerp(w.userData.restZ, w.userData.upZ, current.wingLift);
      w.rotation.x = lerp(w.userData.restX, w.userData.upX, current.wingLift);
    });
    const flutter = Math.sin(time * 14) * 0.08 * current.wingLift;
    wingL.rotation.x += flutter;
    wingR.rotation.x += flutter;

    // ---- blinking (independent of state, rate-modulated) ----
    if (!blinking) {
      nextBlinkIn -= delta;
      if (nextBlinkIn <= 0) {
        blinking = true;
        blinkT = 0;
      }
    } else {
      blinkT += delta / 0.16; // ~160ms blink
      if (blinkT >= 1) {
        blinking = false;
        nextBlinkIn = (1.6 + Math.random() * 2.4) / Math.max(0.2, target.blinkRate);
      }
    }
    const blinkScale = blinking ? 1 - Math.sin(Math.min(blinkT, 1) * Math.PI) : 1;

    [eyeL, eyeR].forEach((e) => {
      e.scale.set(current.eyeScale, current.eyeScale * blinkScale, current.eyeScale);
    });

    // pupils glance side to side while thinking
    const glance = Math.sin(time * 0.8) * 0.05 * current.tilt;
    [eyeL, eyeR].forEach((e) => {
      const p = e.getObjectByName('pupil');
      if (p) p.position.x = glance;
    });

    // ---- beak: mouth-sync to amplitude in 'speaking', gentle idle parting otherwise ----
    const idlePart = (Math.sin(time * 2) * 0.5 + 0.5) * 0.04;
    const speakOpen = stateName === 'speaking' ? amplitude * 0.55 : idlePart;
    lowerPivot.rotation.x = -speakOpen;
  }

  function dispose() {
    group.traverse((obj) => {
      if (obj.geometry) obj.geometry.dispose();
      if (obj.material) obj.material.dispose();
    });
  }

  setState('idle');

  return {
    group,
    update,
    setState,
    setAmplitude,
    dispose,
    get state() {
      return stateName;
    },
  };
}
