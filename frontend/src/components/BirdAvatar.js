// BirdAvatar.js - Skeleton Placeholder
export function createBirdAvatar(THREE, opts = {}) {
  const group = new THREE.Group();
  group.name = 'EduMentorOwlPlaceholder';
  
  console.log("Empty mascot placeholder initialized.");

  return {
    group,
    update: (time, delta) => {},
    setState: (name) => {
      console.log("SetState placeholder:", name);
    },
    setAmplitude: (v) => {},
    dispose: () => {
      console.log("Placeholder disposed.");
    },
    get state() {
      return 'idle';
    },
  };
}
