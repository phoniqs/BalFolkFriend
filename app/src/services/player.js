// Contexte audio partagé et lecture d'un seul morceau à la fois.
let audioContext = null;
let active = null; // { synth, onStop }

export function getAudioContext() {
    if (!audioContext) {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        audioContext = new Ctx();
    }
    return audioContext;
}

export function stopActiveSynth() {
    if (!active) return;
    const { synth, onStop } = active;
    active = null;
    try { synth.stop(); } catch (e) { console.debug(e); }
    if (onStop) onStop();
}

export function setActiveSynth(synth, onStop) {
    stopActiveSynth();
    active = { synth, onStop };
}

export function releaseSynth(synth) {
    if (active && active.synth === synth) active = null;
}