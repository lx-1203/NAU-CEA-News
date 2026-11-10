// Whole expression images stay intact; actual voice drives particles and gentle jitter.
const talkingPrefix = {xiaoXu:'xiaoxu',xiaoHe:'xiaohe'};
const talkingStates = new Map();
const voice = {context:null,analyser:null,source:null,samples:null,raf:0,url:null,active:null,lastSound:0,revision:0};
const voiceAudio = () => document.getElementById('voiceAudio');
const voiceStatus = text => document.getElementById('talkStatus').textContent=text;

function ensureSpeechParticles(id) {
    const character=document.getElementById(id);
    let particles=character.querySelector('.speech-particles');
    if(!particles){
        particles=document.createElement('div');particles.className='speech-particles';particles.setAttribute('aria-hidden','true');
        for(let i=0;i<8;i++){const dot=document.createElement('span');dot.style.setProperty('--i',i);particles.append(dot);}
        character.append(particles);
    }
    return particles;
}

function setVoiceEffect(id,audible) {
    const character=document.getElementById(id);
    character.classList.toggle('voice-active',audible);
    character.dataset.voiceState=audible?'speaking':'silent';
}

async function armVoice(id) {
    stopVoiceEffects();
    if(!talkingPrefix[id]) return false;
    voice.active=id;voice.revision++;
    talkingStates.clear();talkingStates.set(id,{particles:ensureSpeechParticles(id)});
    if(newsMode){document.getElementById('newsAnchor').value=id;updateNewsAnchor();}
    document.getElementById('speakerName').textContent=id==='xiaoXu'?'小序':'小禾';
    return true;
}

async function ensureVoiceAudio() {
    if(!voice.context){
        voice.context=new AudioContext();voice.analyser=voice.context.createAnalyser();
        voice.analyser.fftSize=1024;voice.samples=new Float32Array(voice.analyser.fftSize);
        voice.source=voice.context.createMediaElementSource(voiceAudio());
        voice.source.connect(voice.analyser);voice.analyser.connect(voice.context.destination);
    }
    if(voice.context.state==='suspended') await voice.context.resume();
}

function stopVoiceEffects() {
    cancelAnimationFrame(voice.raf);voice.raf=0;voice.lastSound=0;
    for(const id of Object.keys(talkingPrefix)) setVoiceEffect(id,false);
    document.getElementById('voiceMeter').textContent='音量 0.000';
}

function analyseVoice() {
    cancelAnimationFrame(voice.raf);
    const tick=()=>{
        const audio=voiceAudio();
        if(audio.paused||audio.ended||audio.seeking||!voice.active){stopVoiceEffects();return;}
        voice.analyser.getFloatTimeDomainData(voice.samples);
        const rms=Math.sqrt(voice.samples.reduce((sum,x)=>sum+x*x,0)/voice.samples.length)*(audio.muted?0:audio.volume);
        const threshold=Number(document.getElementById('voiceThreshold').value),now=performance.now();
        if(rms>=threshold) voice.lastSound=now;
        const audible=rms>=threshold || (rms>threshold*.5 && now-voice.lastSound<70);
        setVoiceEffect(voice.active,audible);
        document.getElementById('voiceMeter').textContent=`音量 ${rms.toFixed(3)}`;
        voice.raf=requestAnimationFrame(tick);
    };
    tick();
}

async function beginVoicePlayback() {
    try {
        await ensureVoiceAudio();
        if(!await armVoice(document.getElementById('voiceAnchor').value)) return;
        if(voiceAudio().paused||voiceAudio().seeking){stopVoiceEffects();return;}
        analyseVoice();voiceStatus('配音播报：有声时粒子＋轻抖，停顿时停止；人物使用完整表情图。');
    } catch {voiceAudio().pause();stopVoiceEffects();voiceStatus('音频分析无法启动，请点击“播放配音”重试。');}
}

async function playVoice() {
    if(!voiceAudio().getAttribute('src')){voiceStatus('请先选择本地配音文件。');return;}
    try {await ensureVoiceAudio();await voiceAudio().play();}
    catch {voiceStatus('配音无法播放，请检查音频文件或使用 WAV / MP3。');}
}

async function playVoiceDemo() {
    dialogue.clear();
    clearVoice();
    voiceAudio().muted=false;
    voiceAudio().volume=1;
    try { voiceAudio().src=await loadVoiceDemo(); }
    catch {voiceStatus('未安装示例录音，请选择自己的本地配音文件。');return;}
    voiceAudio().load();
    document.getElementById('subtitleText').textContent='口播示意：有声时粒子＋轻抖，停顿时停止';
    voiceStatus('本地口播示例：如未配置示例音频，请选择自己的配音文件。');
    await playVoice();
}
function pauseVoice(){voiceAudio().pause();stopVoiceEffects();}
function clearVoice(){
    pauseVoice();voice.revision++;voiceAudio().removeAttribute('src');voiceAudio().load();
    if(voice.url) URL.revokeObjectURL(voice.url);voice.url=null;
    voiceStatus('配音已清空，粒子与抖动已停止。');
}

// Compatibility APIs now require actual audio instead of a timed full-sprite loop.
async function startTalking(id){document.getElementById('voiceAnchor').value=id;await playVoice();}
function previewTalking(id){startTalking(id);}
function stopTalking(id,restore=true){
    if(voice.active===id){pauseVoice();voice.revision++;voice.active=null;}
    setVoiceEffect(id,false);talkingStates.delete(id);
}
function stopAllTalking(){pauseVoice();for(const id of [...talkingStates.keys()])stopTalking(id);}

document.addEventListener('DOMContentLoaded',()=>{
    const audio=voiceAudio();
    document.getElementById('voiceFile').addEventListener('change',event=>{
        const file=event.target.files[0];if(!file)return;
        clearVoice();voice.url=URL.createObjectURL(file);audio.src=voice.url;audio.load();
        voiceStatus(`配音已选择：${file.name}。点击播放配音。`);
    });
    document.getElementById('voiceAnchor').addEventListener('change',async()=>{
        const playing=!audio.paused;
        if(await armVoice(document.getElementById('voiceAnchor').value) && playing)analyseVoice();
    });
    audio.addEventListener('playing',beginVoicePlayback);
    for(const event of ['pause','ended','seeking','waiting','emptied']) audio.addEventListener(event,stopVoiceEffects);
    audio.addEventListener('seeked',()=>{if(!audio.paused)beginVoicePlayback();});
    audio.addEventListener('volumechange',()=>{if(audio.muted||audio.volume===0)stopVoiceEffects();else if(!audio.paused)analyseVoice();});
    audio.addEventListener('error',()=>{stopVoiceEffects();voiceStatus('无法解码配音文件，请换用 WAV / MP3。');});
});
