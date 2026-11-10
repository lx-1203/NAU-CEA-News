// 表情映射表（对应需要生成的像素图文件名）
const expressionMap = {
    xiaoXu: {
        normal: 'anchors/generated/xiaoxu-normal.png',
        normal2: 'anchors/frequent-v1/xiaoxu-normal2.png',
        normal3: 'anchors/frequent-v1/xiaoxu-normal3.png',
        happy: 'anchors/generated/xiaoxu-happy.png',
        happy2: 'anchors/frequent-v1/xiaoxu-happy2.png',
        happy3: 'anchors/frequent-v1/xiaoxu-happy3.png',
        surprised: 'anchors/gestures-v2/xiaoxu-surprised.png',
        thinking: 'anchors/gestures-v2/xiaoxu-thinking.png',
        thinking2: 'anchors/frequent-v1/xiaoxu-thinking2.png',
        thinking3: 'anchors/frequent-v1/xiaoxu-thinking3.png',
        serious: 'anchors/generated/xiaoxu-serious.png',
        presenting: 'anchors/gestures-v2/xiaoxu-presenting.png',
        presenting2: 'anchors/frequent-v1/xiaoxu-presenting2.png',
        presenting3: 'anchors/frequent-v1/xiaoxu-presenting3.png',
        thumbsup: 'anchors/gestures-v2/xiaoxu-thumbsup.png',
        wave: 'anchors/common-v1/xiaoxu-wave.png'
    },
    xiaoHe: {
        normal: 'anchors/generated/xiaohe-normal.png',
        normal2: 'anchors/frequent-v1/xiaohe-normal2.png',
        normal3: 'anchors/frequent-v1/xiaohe-normal3.png',
        happy: 'anchors/generated/xiaohe-happy.png',
        happy2: 'anchors/frequent-v1/xiaohe-happy2.png',
        happy3: 'anchors/frequent-v1/xiaohe-happy3.png',
        surprised: 'anchors/common-v1/xiaohe-surprised.png',
        thinking: 'anchors/common-v1/xiaohe-thinking.png',
        thinking2: 'anchors/frequent-v1/xiaohe-thinking2.png',
        thinking3: 'anchors/frequent-v1/xiaohe-thinking3.png',
        serious: 'anchors/common-v1/xiaohe-serious.png',
        presenting: 'anchors/common-v1/xiaohe-presenting.png',
        presenting2: 'anchors/frequent-v1/xiaohe-presenting2.png',
        presenting3: 'anchors/frequent-v1/xiaohe-presenting3.png',
        thumbsup: 'anchors/common-v1/xiaohe-thumbsup.png',
        excited: 'anchors/gestures-v2/xiaohe-excited.png',
        shy: 'anchors/gestures-v2/xiaohe-shy.png',
        wink: 'anchors/generated/xiaohe-wink.png',
        wave: 'anchors/gestures-v2/xiaohe-wave.png',
        encourage: 'anchors/gestures-v2/xiaohe-encourage.png'
    }
};

const expressionTimers = new WeakMap();

// 切换角色表情
function changeExpression(characterId, expression) {
    const character = document.getElementById(characterId);
    if (!character || !expressionMap[characterId]?.[expression]) return;
    const sprite = character.querySelector('.character-sprite');
    
    if (sprite && expressionMap[characterId][expression]) {
        // 添加说话动画
        clearTimeout(expressionTimers.get(character));
        character.classList.remove('speaking');
        void sprite.offsetWidth;
        character.classList.add('speaking');
        
        // 切换图片
        sprite.src = `assets/characters/${expressionMap[characterId][expression]}`;
        sprite.dataset.expression = expression;
        if (newsMode) { document.getElementById('newsAnchor').value = characterId; updateNewsAnchor(); }
        document.getElementById('speakerName').textContent = characterId === 'xiaoXu' ? '小序' : '小禾';
        
        // 回弹效果
        expressionTimers.set(character, setTimeout(() => {
            character.classList.remove('speaking');
        }, 600));
    }
}

// 更新字幕
function updateSubtitle() {
    const input = document.getElementById('subtitleInput');
    const subtitle = document.getElementById('subtitleText');
    
    if (input.value.trim()) {
        subtitle.textContent = input.value;
        input.value = '';
    }
}

// 更新日期时间
function updateDateTime() {
    const dateElement = document.getElementById('subtitleDate');
    const now = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }));
    
    const month = (now.getMonth() + 1).toString().padStart(2, '0');
    const day = now.getDate().toString().padStart(2, '0');
    const hours = now.getHours().toString().padStart(2, '0');
    const minutes = now.getMinutes().toString().padStart(2, '0');
    
    dateElement.textContent = `${month}月${day}日 ${hours}:${minutes}`;
}

// 演播室特效
class StudioEffects {
    constructor() {
        this.initCameraZoom();
        this.initStickers();
    }
    
    // 镜头推进效果
    initCameraZoom() {
        const studio = document.querySelector('.studio-container');
        let zoomLevel = 1;
        
        window.cameraZoom = (targetZoom, duration = 2000) => {
            const startZoom = zoomLevel;
            const startTime = Date.now();
            
            function animate() {
                const elapsed = Date.now() - startTime;
                const progress = Math.min(elapsed / duration, 1);
                
                // 使用 ease-in-out
                const eased = progress < 0.5
                    ? 2 * progress * progress
                    : 1 - Math.pow(-2 * progress + 2, 2) / 2;
                
                zoomLevel = startZoom + (targetZoom - startZoom) * eased;
                studio.style.transform = `scale(${zoomLevel})`;
                
                if (progress < 1) {
                    requestAnimationFrame(animate);
                }
            }
            
            animate();
        };
    }
    
    // 贴纸动画系统
    initStickers() {
        window.addSticker = (type, x, y) => {
            const sticker = document.createElement('div');
            sticker.className = `sticker sticker-${type}`;
            sticker.textContent = type === 'code' ? '{ }' : '✦';
            sticker.style.left = `${x}%`;
            sticker.style.top = `${y}%`;
            
            const container = document.querySelector('.studio-container');
            container.appendChild(sticker);
            
            // 拉伸回弹动画
            sticker.style.animation = 'stickerPop 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)';
            
            setTimeout(() => {
                sticker.remove();
            }, 3000);
        };
        

    }
}

// 对话系统
class DialogueSystem {
    constructor() {
        this.queue = [];
        this.isPlaying = false;
        this.generation = 0;
    }
    
    // 添加对话到队列
    add(characterId, expression, text, duration = 3000) {
        this.queue.push({ characterId, expression, text, duration });
        if (!this.isPlaying) {
            this.playNext();
        }
    }
    
    // 播放下一句
    async playNext() {
        if (this.queue.length === 0) {
            stopAllTalking();
            this.isPlaying = false;
            return;
        }
        
        this.isPlaying = true;
        const generation = this.generation;
        const { characterId, expression, text, duration } = this.queue.shift();
        
        stopAllTalking();
        // 切换表情
        changeExpression(characterId, expression);
        
        // 更新字幕
        document.getElementById('subtitleText').textContent = text;
        
        // 等待指定时长
        await new Promise(resolve => setTimeout(resolve, duration));
        if (generation !== this.generation) return;
        
        // 播放下一句
        this.playNext();
    }
    
    // 清空队列
    clear() {
        stopAllTalking();
        this.generation++;
        this.queue = [];
        this.isPlaying = false;
    }
}

// 全局初始化
let studioEffects;
let dialogueSystem;

document.addEventListener('DOMContentLoaded', () => {
    // 初始化日期时间
    updateDateTime();
    setInterval(updateDateTime, 60000); // 每分钟更新
    
    // 初始化特效系统
    studioEffects = new StudioEffects();
    dialogueSystem = new DialogueSystem();
    
    // 暴露到全局
    window.dialogue = dialogueSystem;
    
    console.log('NJAU-CEA 新闻联播系统已就绪');
    console.log('使用方法：');
    console.log('1. changeExpression(characterId, expression) - 切换表情');
    console.log('2. cameraZoom(level, duration) - 镜头推进');
    console.log('3. addSticker(type, x, y) - 添加贴纸');
    console.log('4. dialogue.add(characterId, expression, text, duration) - 添加对话');
});

// 示例对话脚本
function playDemo() {
    dialogue.clear();
    dialogue.add('xiaoXu', 'normal', '大家好，我是秾小序！', 2500);
    dialogue.add('xiaoHe', 'happy', '我是楠小禾！欢迎收看 NJAU-CEA 新闻联播！', 3000);
    dialogue.add('xiaoXu', 'happy', '今天我们有很多精彩内容要跟大家分享~', 3000);
    dialogue.add('xiaoHe', 'excited', '让我们一起来看看吧！', 2500);
}

// 键盘快捷键
document.addEventListener('keydown', (e) => {
    if (e.code === 'Escape') document.body.classList.remove('broadcast-mode');
    if (e.target.matches('input, textarea, select, [contenteditable="true"]')) return;
    // 空格键播放演示
    if (e.code === 'Space' && e.target.tagName !== 'INPUT') {
        e.preventDefault();
        playDemo();
    }
    
    // 数字键切换表情
    if (e.key >= '1' && e.key <= '5') {
        const expressions = ['normal', 'happy', 'surprised', 'thinking', 'serious'];
        changeExpression('xiaoXu', expressions[parseInt(e.key) - 1]);
    }
});

function toggleBroadcast() {
    document.body.classList.toggle('broadcast-mode');
}
