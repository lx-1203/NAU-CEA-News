// Local-only news material playlist; no file upload or server required.
let newsItems = [];
let newsIndex = -1;
let newsMode = false;

// One programme asset for the studio screen and lower-left mark. Also called by
// offline exports: no autoplay, video decoding or date-specific page patch needed.
function applyStudioBranding({ending=false,date=''}={}) {
    const programme=document.querySelector('.branding-program-mark img');
    const screen=document.getElementById('studioProgrammeLogo');
    const source=programme.getAttribute('src');
    if(!source)throw new Error('节目LOGO缺失，不能导出文字替代版');
    if(screen.getAttribute('src')!==source)screen.setAttribute('src',source);
    document.querySelector('.branding-screen').dataset.phase=ending?'outro':'intro';
    if(date)document.querySelector('.screen-tag i').textContent=date+' · 每日科技';
    const box=screen.getBoundingClientRect();
    return {phase:ending?'outro':'intro',source:screen.src,width:box.width,height:box.height};
}

// The same editorial interface is used by offline daily renders and local previews.
function applyNewsEditorialLayout({facts, layout='photo', caption, source}) {
    document.querySelector('.news-side-label>b').textContent = document.querySelector('#newsAnchor').value === 'xiaoHe' ? '小禾划重点' : '小序划重点';
    const list = document.querySelector('.news-key-facts');
    list.replaceChildren(...facts.map(text => {
        const li = document.createElement('li');
        li.textContent = text;
        return li;
    }));
    document.querySelector('.news-scene').dataset.mediaLayout = layout;
    const captionNode = document.querySelector('#newsMaterialCaption');
    const kind = document.createElement('span');
    kind.className = 'material-kind';
    kind.textContent = caption;
    const origin = document.createElement('small');
    origin.className = 'material-origin';
    origin.textContent = source;
    captionNode.replaceChildren(kind, origin);
    const image = document.getElementById('newsImage');
    const windowNode = document.querySelector('.news-media-window');
    if (image.src) windowNode.style.setProperty('--news-backdrop-image', 'url('+JSON.stringify(image.src)+')');
    const topic = document.querySelector('.topic-bar');
    topic.querySelector('span:first-child').textContent = '来源';
    topic.querySelector('span:nth-child(2)').textContent = source;
    fitNewsBubble();
}

function fitNewsBubble() {
    const bubble=document.querySelector('.news-side-label');
    const frame=document.querySelector('.tv-frame').getBoundingClientRect();
    const host=document.getElementById(document.querySelector('#newsAnchor').value).getBoundingClientRect();
    const minimumTop=frame.height*.17, maximumBottom=host.top-frame.top-frame.width*.014-14;
    let font=frame.width*.0148;
    bubble.style.setProperty('--news-fact-font',font+'px');
    while(bubble.offsetHeight>maximumBottom-minimumTop && font>24) {
        font=Math.max(24,font-.5);bubble.style.setProperty('--news-fact-font',font+'px');
    }
    bubble.style.setProperty('--news-bubble-top',Math.max(minimumTop,Math.min(frame.height*.24,maximumBottom-bubble.offsetHeight))+'px');
}

// Full-edition headlines stay independent of the current material's source.
function setNewsTicker(headlines, durationSeconds = 0) {
    const items = headlines.map(text => String(text).trim()).filter(Boolean);
    if (!items.length) throw new Error('快讯至少需要一条当期摘要');
    const ticker = document.querySelector('.ticker');
    const text = ticker.querySelector('span');
    const content = items.join('　　◆　　');
    ticker.querySelector('b').textContent = '快讯';
    text.setAttribute('aria-label', items.join('；'));
    const measure = () => {
        const style = getComputedStyle(text);
        const fontSize = parseFloat(style.fontSize);
        const context = document.createElement('canvas').getContext('2d');
        context.font = style.font;
        const contentWidth = context.measureText(content).width;
        const viewportWidth = ticker.querySelector('div').getBoundingClientRect().width;
        // One screen of separation prevents an early second pass in a finite film.
        const cycle = content + '　'.repeat(Math.ceil(viewportWidth / fontSize) + 4);
        text.textContent = cycle + cycle;
        const scale = document.querySelector('.tv-frame').getBoundingClientRect().width / 1920;
        const speed = durationSeconds > 0 ? contentWidth / durationSeconds : 60 * scale;
        text.style.animationDuration = `${text.scrollWidth / 2 / speed}s`;
    };
    measure();
    document.fonts.ready.then(measure);
}

function updateNewsAnchor() {
    const anchor = document.getElementById('newsAnchor').value;
    document.querySelector('.tv-frame').dataset.newsAnchor = anchor;
    document.getElementById('newsPresenterName').firstChild.textContent = anchor === 'xiaoXu' ? '秾小序 ' : '楠小禾 ';
    if (newsMode) document.getElementById('speakerName').textContent = anchor === 'xiaoXu' ? '小序' : '小禾';
}

function setNewsScene(enabled) {
    newsMode = Boolean(enabled);
    document.querySelector('.tv-frame').classList.toggle('is-news', newsMode);
    document.querySelector('.news-scene').hidden = !newsMode;
    document.getElementById('studioTab').setAttribute('aria-pressed', String(!newsMode));
    document.getElementById('newsTab').setAttribute('aria-pressed', String(newsMode));
    if (!newsMode) document.getElementById('newsVideo').pause();
    if (!newsMode) {
        applyStudioBranding();
        document.querySelector('.topic-bar>span:first-child').textContent = '校园科技联播';
        document.querySelector('.topic-bar>span:nth-child(2)').textContent = '每日科技 · 前一日资讯回顾';
    }
    updateNewsAnchor();
}

function clearNewsMedia() {
    const video = document.getElementById('newsVideo');
    video.pause();
    video.removeAttribute('src');
    video.load();
    document.getElementById('newsImage').removeAttribute('src');
    for (const item of newsItems) if (item.local) URL.revokeObjectURL(item.url);
    newsItems = [];
    newsIndex = -1;
    document.getElementById('newsFiles').value = '';
    renderNewsMaterial();
}

function renderNewsMaterial() {
    const image = document.getElementById('newsImage');
    const video = document.getElementById('newsVideo');
    const item = newsItems[newsIndex];
    video.pause();
    image.hidden = !item || item.kind !== 'image';
    video.hidden = !item || item.kind !== 'video';
    document.getElementById('newsEmpty').hidden = Boolean(item);
    if (item?.kind === 'image') {
        video.removeAttribute('src');
        video.load();
        image.src = item.url;
        image.alt = item.name;
    } else if (item?.kind === 'video') {
        image.removeAttribute('src');
        video.src = item.url;
        video.load();
    }
    const list = document.getElementById('newsPlaylist');
    list.replaceChildren();
    newsItems.forEach((entry,index) => {
        const option = document.createElement('option');
        option.value = String(index);
        option.textContent = `${index + 1}. ${entry.name}`;
        list.appendChild(option);
    });
    if (!newsItems.length) list.add(new Option('尚未选择素材',''));
    list.value = item ? String(newsIndex) : '';
    document.getElementById('newsMaterialCaption').textContent = item?.name || '请选择图片或视频';
    document.getElementById('newsCounter').textContent = `${String(newsIndex+1).padStart(2,'0')} / ${String(newsItems.length).padStart(2,'0')}`;
    document.getElementById('previousNews').disabled = newsIndex <= 0;
    document.getElementById('nextNews').disabled = newsIndex >= newsItems.length-1;
    document.getElementById('playNewsVideo').disabled = item?.kind !== 'video';
    document.getElementById('newsStatus').textContent = item ? `${item.kind === 'video' ? '视频已载入，点击播放；浏览器不支持的编码需先转换。' : '图片已载入，按原比例完整显示。'} 素材仅保留在当前页面。` : '请选择本地图片或视频；刷新页面后需重新选择。';
}

function stepNewsMaterial(offset) {
    const next = newsIndex + offset;
    if (next >= 0 && next < newsItems.length) {
        newsIndex = next;
        renderNewsMaterial();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    setNewsTicker([document.querySelector('.ticker span').textContent], Number(document.querySelector('.ticker').dataset.duration) || 0);
    document.getElementById('newsAnchor').addEventListener('change',updateNewsAnchor);
    document.getElementById('updateNewsTitle').addEventListener('click',() => {
        const title = document.getElementById('newsTitleInput').value.trim();
        if (title) document.getElementById('newsTitle').textContent = title;
    });
    document.getElementById('newsFiles').addEventListener('change', event => {
        const files = [...event.target.files];
        const accepted = files.filter(file => /^(image|video)\//.test(file.type) || /\.(png|jpe?g|webp|gif|avif|mp4|webm|mov|ogv)$/i.test(file.name));
        if (!accepted.length) {
            document.getElementById('newsStatus').textContent = '未找到支持的图片或视频，请重新选择。';
            return;
        }
        clearNewsMedia();
        newsItems = accepted.map(file => ({name:file.name,kind:file.type.startsWith('video/') || /\.(mp4|webm|mov|ogv)$/i.test(file.name) ? 'video' : 'image',url:URL.createObjectURL(file),local:true}));
        newsIndex = 0;
        setNewsScene(true);
        renderNewsMaterial();
    });
    document.getElementById('newsPlaylist').addEventListener('change',event => {
        if (event.target.value !== '') { newsIndex = Number(event.target.value); renderNewsMaterial(); }
    });
    document.getElementById('previousNews').addEventListener('click',()=>stepNewsMaterial(-1));
    document.getElementById('nextNews').addEventListener('click',()=>stepNewsMaterial(1));
    document.getElementById('clearNews').addEventListener('click',clearNewsMedia);
    document.getElementById('showSampleNews').addEventListener('click',()=>{
        clearNewsMedia();
        newsItems = [{name:'协会 IP 形象参考 · 示例素材',kind:'image',url:'assets/references/mascots.png',local:false}];
        newsIndex = 0;
        setNewsScene(true);
        renderNewsMaterial();
    });
    document.getElementById('playNewsVideo').addEventListener('click',async()=>{
        const video = document.getElementById('newsVideo');
        if (video.paused) {
            try { await video.play(); }
            catch { document.getElementById('newsStatus').textContent = '无法播放该视频，请检查文件或改用 H.264 MP4 / WebM。'; }
        } else video.pause();
    });
    for (const id of ['newsImage','newsVideo']) document.getElementById(id).addEventListener('error',()=>{
        document.getElementById('newsStatus').textContent = '当前素材无法读取，请换一张图片或使用浏览器支持的视频编码。';
    });
    updateNewsAnchor();
    renderNewsMaterial();
    applyStudioBranding();
});
