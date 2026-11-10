/* Reusable bottom navigation: all segment positions come from final timeline data. */
(()=>{
  const nav=JSON.parse(document.querySelector('#news-navigation').textContent);
  const root=document.querySelector('.news-player'),video=root.querySelector('video');
  const seek=root.querySelector('.seek'),played=root.querySelector('.played-track');
  const play=root.querySelector('.play'),clock=root.querySelector('.clock');
  const current=root.querySelector('.current-chapter');
  const format=t=>{t=Math.max(0,Math.floor(t));return `${String(Math.floor(t/60)).padStart(2,'0')}:${String(t%60).padStart(2,'0')}`};
  let scrubbing=false;
  function jump(t){if(video.readyState<1)return;video.currentTime=Math.max(0,Math.min(video.duration,t));update()}
  function button(title,time,container){
    const b=document.createElement('button');b.type='button';b.dataset.start=time;b.textContent=title;
    b.addEventListener('click',()=>jump(time));container.append(b);return b;
  }
  for(const s of nav.sections){
    const segment=document.createElement('span');segment.style.left=`${s.start/nav.duration*100}%`;
    segment.style.width=`${(s.end-s.start)/nav.duration*100}%`;root.querySelector('.section-track').append(segment);
    const b=button(s.title,s.start,root.querySelector('.section-buttons'));b.dataset.end=s.end;
  }
  for(const c of nav.chapters){
    const mark=document.createElement('i');mark.style.left=`${c.start/nav.duration*100}%`;root.querySelector('.chapter-marks').append(mark);
    const b=button('',c.start,document.querySelector('.chapter-list'));b.dataset.end=c.end;
    const time=document.createElement('time');time.textContent=format(c.start);
    const text=document.createElement('span');text.textContent=(c.section_title?`${c.section_title} · `:'')+c.title;b.append(time,text);
    b.setAttribute('aria-label',`${format(c.start)}，${c.title}`);
  }
  function update(){
    const duration=Number.isFinite(video.duration)&&video.duration>0?video.duration:nav.duration;
    const time=video.currentTime||0;seek.max=duration;if(!scrubbing)seek.value=time;
    seek.setAttribute('aria-valuetext',`${format(time)}，总长${format(duration)}`);
    played.style.width=`${Math.max(0,Math.min(100,time/duration*100))}%`;
    clock.textContent=`${format(time)} / ${format(duration)}`;play.textContent=video.paused?'播放':'暂停';
    const c=nav.chapters.find(c=>time>=c.start&&time<c.end)||nav.chapters.at(-1);
    current.textContent=c?c.title:'';
    document.querySelectorAll('[data-start][data-end]').forEach(b=>b.setAttribute('aria-current',String(time>=Number(b.dataset.start)&&time<Number(b.dataset.end))));
  }
  seek.addEventListener('pointerdown',()=>{scrubbing=true});
  seek.addEventListener('input',()=>jump(Number(seek.value)));
  seek.addEventListener('change',()=>{scrubbing=false;jump(Number(seek.value))});
  seek.addEventListener('pointerup',()=>{scrubbing=false;update()});
  seek.addEventListener('pointercancel',()=>{scrubbing=false;update()});
  play.addEventListener('click',async()=>{if(video.paused){try{await video.play()}catch{play.textContent='点击视频播放'}}else video.pause()});
  const mute=root.querySelector('.mute');
  function volume(){mute.textContent=video.muted?'开声':'静音';mute.setAttribute('aria-label',video.muted?'取消静音':'静音');mute.setAttribute('aria-pressed',String(video.muted))}
  mute.addEventListener('click',()=>{video.muted=!video.muted});video.addEventListener('volumechange',volume);volume();
  root.querySelector('.fullscreen').addEventListener('click',async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await root.requestFullscreen()}catch{document.querySelector('.player-note').textContent='当前环境不支持全屏，可继续使用拖动和章节跳转。'}});
  for(const event of ['timeupdate','loadedmetadata','durationchange','play','pause','seeked','ended'])video.addEventListener(event,update);
  video.addEventListener('error',()=>{document.querySelector('.player-note').textContent='视频暂时无法读取，请确认视频与播放器文件的位置。'});
  update();window.newsPlayer={jump,update,navigation:nav};
  // Keep native controls as a no-JavaScript fallback; avoid two progress bars.
  video.controls=false;
})();
