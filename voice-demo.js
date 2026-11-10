// Optional local audio. Public framework does not embed or distribute recordings.
const voiceDemoData="assets/audio/voice-demo.wav";
async function loadVoiceDemo() {
    if (location.protocol !== 'file:') return voiceDemoData;
    if (window.localVoiceDemoData) return window.localVoiceDemoData;
    await new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'assets/audio/voice-demo-data.js';
        script.onload = resolve;
        script.onerror = () => reject(new Error('Local demo recording is not installed'));
        document.head.appendChild(script);
    });
    if (!window.localVoiceDemoData) throw new Error('Local demo recording is not installed');
    return window.localVoiceDemoData;
}
